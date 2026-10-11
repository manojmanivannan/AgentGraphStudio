"""MCP tool descriptor pipeline (ticket #138, spec §4.1–4.2 and §4.5).

Unit seam: ``runner.mcp_tools.build_mcp_tool`` turns one server ``tools/list``
entry (an ``mcp.types.Tool``) plus the Tool Node's grant into a DSPy-ready
async callable carrying ``__name__`` / ``__doc__`` / ``requires_approval`` /
``node_id`` exactly like a compiled author tool — no new execution path.
"""

import uuid

import mcp.types as mcp_types
import pytest

from canvas_server.runner.mcp_tools import (
    MCP_RESULT_MAX_CHARS,
    MCP_UNTRUSTED_CLOSE,
    MCP_UNTRUSTED_OPEN,
    build_mcp_tool,
    format_mcp_result,
    sanitize_tool_name,
)


class RecordingSession:
    """The ``_MCPToolClient`` protocol: records call_tool invocations."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments))
        return self.result


def make_server_tool(name="add", description="Add two integers.", schema=None):
    if schema is None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "first"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }
    return mcp_types.Tool(name=name, description=description, inputSchema=schema)


def text_result(*texts, is_error=False):
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=t) for t in texts],
        isError=is_error,
    )


def make_descriptor(session, tool=None, requires_approval=False):
    tool = tool or make_server_tool()
    return build_mcp_tool(
        session,
        tool,
        node_id=uuid.uuid4(),
        requires_approval=requires_approval,
    )


class TestSanitizeToolName:
    def test_illegal_characters_become_underscores(self):
        assert sanitize_tool_name("my-tool.v2") == "my_tool_v2"

    def test_leading_digit_is_prefixed(self):
        assert sanitize_tool_name("3d-render") == "_3d_render"

    def test_empty_name_falls_back_to_placeholder(self):
        assert sanitize_tool_name("") == "mcp_tool"


class TestDescriptorBuild:
    async def test_server_arg_types_are_preserved(self):
        tool = make_descriptor(RecordingSession(text_result("3")))

        assert set(tool.args) == {"a", "b"}
        assert tool.arg_types["a"] is int
        assert tool.arg_types["b"] is int
        assert "(Required)" in tool.arg_desc["a"]

    async def test_call_routes_to_the_original_server_name(self):
        session = RecordingSession(text_result("3"))
        tool = make_descriptor(session, make_server_tool(name="add"))

        observation = await tool.acall(a=1, b=2)

        # The framing (spec §5.2) wraps the result; the value is inside.
        assert "3" in observation
        assert observation.endswith(MCP_UNTRUSTED_CLOSE)
        # The LLM sees the sanitized name, but the server is called with the
        # name from its own catalog.
        assert session.calls == [("add", {"a": 1, "b": 2})]

    async def test_callables_carry_name_doc_approval_and_node_id(self):
        node_id = uuid.uuid4()
        session = RecordingSession(text_result("3"))
        fn = build_mcp_tool(session, make_server_tool(), node_id=node_id,
                            requires_approval=True).func

        # StreamingReAct unwraps ``tool_obj.func`` and reads these attributes
        # for HITL gating and event enrichment — same contract as author tools.
        assert callable(fn)
        assert fn.requires_approval is True
        assert fn.node_id == node_id
        assert fn.__name__ == "add"
        assert "Add two integers" in fn.__doc__

    async def test_exotic_names_are_sanitized_at_descriptor_build(self):
        session = RecordingSession(text_result("ok"))
        tool = make_descriptor(session, make_server_tool(name="search.web v2"))

        await tool.acall(query="x")  # routed with the original server name
        assert tool.name == "search_web_v2"
        assert tool.func.__name__ == "search_web_v2"
        assert session.calls == [("search.web v2", {"query": "x"})]

    async def test_unprocessable_schema_becomes_failed_stub(self):
        # A schema the DSPy adapter cannot process (``input_schema`` missing,
        # bypassing SDK validation via model_construct).
        broken = mcp_types.Tool.model_construct(
            name="broken", description=None, inputSchema=None
        )
        tool = make_descriptor(RecordingSession(text_result("x")), broken)

        assert tool.name == "broken"
        # Raises at call time → StreamingReAct converts it to an observation.
        with pytest.raises(AttributeError):
            await tool.acall()

    async def test_failed_stub_still_carries_metadata(self):
        broken = mcp_types.Tool.model_construct(
            name="broken", description=None, inputSchema=None
        )
        node_id = uuid.uuid4()
        tool = build_mcp_tool(
            RecordingSession(text_result("x")), broken,
            node_id=node_id, requires_approval=False,
        )

        assert tool.func.node_id == node_id
        assert tool.func.__name__ == "broken"


def image_block():
    return mcp_types.ImageContent(type="image", data="aGk=", mimeType="image/png")


def audio_block():
    return mcp_types.AudioContent(type="audio", data="aGk=", mimeType="audio/wav")


def mixed_result():
    return mcp_types.CallToolResult(
        content=[
            mcp_types.TextContent(type="text", text="t1"),
            image_block(),
            mcp_types.TextContent(type="text", text="t2"),
            mcp_types.TextContent(type="text", text="t3"),
        ]
    )


class TestResultFraming:
    """Spec §4.5: text blocks joined; non-text blocks → placeholder note;
    50k cap with truncation note; isError never raises. §5.2 (#140): the
    observation is wrapped in untrusted-data delimiters with explicit
    framing — the cap remains the only truncation."""

    def test_single_text_block_is_delimited_untrusted_data(self):
        observation, raw = format_mcp_result(text_result("3"))
        assert observation.startswith("[")
        assert "untrusted" in observation.lower()
        assert observation.endswith(MCP_UNTRUSTED_CLOSE)
        # original content appears between the delimiters
        assert "3" in observation
        assert raw[0]["type"] == "text" and raw[0]["text"] == "3"

    def test_multiple_text_blocks_are_joined_between_delimiters(self):
        observation, _ = format_mcp_result(text_result("t1", "t2", "t3"))
        inner = observation.split(MCP_UNTRUSTED_OPEN, 1)[1]
        inner = inner.rsplit(MCP_UNTRUSTED_CLOSE, 1)[0]
        assert "t1\nt2\nt3" in inner

    def test_framing_names_the_tool_when_known(self):
        observation, _ = format_mcp_result(text_result("5"), tool_name="add")
        assert "'add'" in observation
        assert observation.endswith(MCP_UNTRUSTED_CLOSE)

    def test_non_text_blocks_become_a_placeholder_note(self):
        observation, _ = format_mcp_result(mixed_result())
        assert "[1 image block returned, 3 text blocks]" in observation

    def test_non_text_only_results_are_all_note(self):
        observation, _ = format_mcp_result(
            mcp_types.CallToolResult(content=[image_block()])
        )
        assert "[1 image block returned]" in observation
        assert MCP_UNTRUSTED_OPEN in observation

    def test_multiple_non_text_counts_summarized_per_type(self):
        observation, _ = format_mcp_result(
            mcp_types.CallToolResult(
                content=[image_block(), image_block(), audio_block()]
            )
        )
        assert "[2 image blocks returned, 1 audio block returned]" in observation

    def test_empty_result_is_still_framed(self):
        observation, raw = format_mcp_result(mcp_types.CallToolResult(content=[]))
        assert MCP_UNTRUSTED_OPEN in observation
        assert MCP_UNTRUSTED_CLOSE in observation
        assert raw == []

    async def test_is_error_is_an_ordinary_framed_observation(self):
        # dspy 3.4.0's convert_mcp_tool raises RuntimeError for isError — the
        # framed observation must never raise, run continues (spec §4.5).
        session = RecordingSession(text_result("ValueError: boom", is_error=True))
        tool = make_descriptor(session)
        observation = await tool.acall(a=1, b=2)
        assert "ValueError: boom" in observation
        assert MCP_UNTRUSTED_OPEN in observation and observation.endswith(
            MCP_UNTRUSTED_CLOSE
        )

    async def test_big_output_is_capped_with_truncation_note(self):
        session = RecordingSession(text_result("A" * 60_000))
        tool = make_descriptor(session)
        observation = await tool.acall(a=1, b=2)

        # The cap is the only truncation (spec §5.2) and stays inside the
        # untrusted-data delimiters.
        inner = observation.split(MCP_UNTRUSTED_OPEN, 1)[1].rsplit(
            MCP_UNTRUSTED_CLOSE, 1
        )[0]
        assert "A" * MCP_RESULT_MAX_CHARS in inner
        assert "truncated" in observation
        assert len(inner) <= MCP_RESULT_MAX_CHARS + 100
        assert observation.endswith(MCP_UNTRUSTED_CLOSE)

    async def test_callables_mark_mcp_origin(self):
        # §5.3: StreamingReAct's call-time approval block keys off this flag —
        # only tools originating from an external MCP server are hard-blocked
        # when no approval client is wired; author tools keep legacy behavior.
        fn = make_descriptor(RecordingSession(text_result("3"))).func
        assert fn.mcp_origin is True
        assert fn.requires_approval is False

    async def test_raw_content_blocks_are_json_safe_and_ride_the_callable(self):
        session = RecordingSession(mixed_result())
        tool = make_descriptor(session)
        await tool.acall(a=1, b=2)

        raw = tool.func.last_raw_content_blocks
        assert isinstance(raw, list) and len(raw) == 4
        assert raw[0]["type"] == "text" and raw[0]["text"] == "t1"
        assert raw[1]["type"] == "image"
        assert raw[1]["mimeType"] == "image/png"

    async def test_raw_blocks_reset_per_call(self):
        session = RecordingSession(mixed_result())
        tool = make_descriptor(session)
        await tool.acall(a=1, b=2)
        session.result = text_result("only text")
        await tool.acall(a=1, b=2)

        raw = tool.func.last_raw_content_blocks
        assert len(raw) == 1 and raw[0]["text"] == "only text"

    async def test_transport_failure_raises_for_the_tool_error_seam(self):
        class BrokenSession:
            async def call_tool(self, name, arguments=None):
                raise ConnectionError("server gone")

        tool = make_descriptor(BrokenSession())
        with pytest.raises(ConnectionError):
            await tool.acall(a=1, b=2)


class TestPerCallTimeout:
    """Spec §4.4: the configured per-call timeout wraps the MCP call; a
    timeout surfaces as the standard ``timed out after <n>s`` execution error
    observation and never fails the run."""

    async def test_slow_call_raises_timeout_with_the_configured_seconds(
        self, monkeypatch
    ):
        import asyncio

        from canvas_server.config import settings

        class SlowSession:
            async def call_tool(self, name, arguments=None):
                await asyncio.sleep(5.0)
                return text_result("3")

        monkeypatch.setattr(settings, "mcp_tool_call_timeout_seconds", 0.2)
        tool = make_descriptor(SlowSession())
        with pytest.raises(TimeoutError, match="timed out after 0.2s"):
            await tool.acall(a=1, b=2)

    async def test_fast_call_is_unaffected_by_the_timeout(self, monkeypatch):
        from canvas_server.config import settings

        monkeypatch.setattr(settings, "mcp_tool_call_timeout_seconds", 0.2)
        session = RecordingSession(text_result("3"))
        tool = make_descriptor(session)
        observation = await tool.acall(a=1, b=2)
        assert observation == "3"
        assert session.calls == [("add", {"a": 1, "b": 2})]


class TestStaleSessionRehandshake:
    """Spec §4.6: exactly one re-handshake on a mid-run stale session, then
    the call retries; non-stale failures never trigger a re-handshake."""

    def _fake_configs(self, obs):
        from canvas_server.mcp_config import McpServerConfig
        from canvas_server.runner.mcp_sessions import McpSessionRegistry

        cfg = McpServerConfig(
            id=uuid.uuid4(),
            name="stale-ref",
            url=obs.url,
            credential_header=None,
            credential_value=None,
        )
        return McpSessionRegistry(servers=(cfg,)), cfg

    async def test_stale_session_rehandshakes_once_then_the_call_succeeds(
        self, make_ref_mcp_server
    ):

        obs = make_ref_mcp_server(tools=("add",), stale_calls="once")
        reg, cfg = self._fake_configs(obs)
        await reg.open([cfg.id])
        listing = {t.name: t for t in await reg.list_tools(cfg.id)}
        tool = build_mcp_tool(
            reg.get_session(cfg.id),
            listing["add"],
            node_id=uuid.uuid4(),
            requires_approval=False,
            session_registry=reg,
            server_id=cfg.id,
        )

        observation = await tool.acall(a=2, b=3)

        assert observation == "5"
        assert obs.initialize_count == 2  # exactly one re-handshake
        await reg.close()

    async def test_always_stale_retries_once_then_raises(self, make_ref_mcp_server):
        from mcp.shared.exceptions import McpError

        obs = make_ref_mcp_server(tools=("add",), stale_calls="always")
        reg, cfg = self._fake_configs(obs)
        await reg.open([cfg.id])
        listing = {t.name: t for t in await reg.list_tools(cfg.id)}
        tool = build_mcp_tool(
            reg.get_session(cfg.id),
            listing["add"],
            node_id=uuid.uuid4(),
            requires_approval=False,
            session_registry=reg,
            server_id=cfg.id,
        )

        with pytest.raises(McpError, match="Session terminated"):
            await tool.acall(a=2, b=3)

        assert obs.initialize_count == 2  # one re-handshake, no retry loop
        await reg.close()

    async def test_non_stale_failure_never_triggers_a_rehandshake(self):
        class CountingRegistry:
            def __init__(self):
                self.rehandshakes = 0

            async def rehandshake(self, server_id):
                self.rehandshakes += 1
                return None

        class FailingSession:
            async def call_tool(self, name, arguments=None):
                raise ConnectionError("connection reset by peer")

        registry = CountingRegistry()
        tool = build_mcp_tool(
            FailingSession(),
            make_server_tool(),
            node_id=uuid.uuid4(),
            requires_approval=False,
            session_registry=registry,
            server_id=uuid.uuid4(),
        )
        with pytest.raises(ConnectionError):
            await tool.acall(a=1, b=2)
        assert registry.rehandshakes == 0

    async def test_is_stale_session_error_walks_exception_groups(self):
        from canvas_server.runner.mcp_sessions import is_stale_session_error

        wrapped = ExceptionGroup(
            "unhandled errors in a TaskGroup",
            [RuntimeError("Session terminated")],
        )
        assert is_stale_session_error(wrapped)
        assert is_stale_session_error(RuntimeError("Session not found"))
        assert not is_stale_session_error(ConnectionError("server gone"))
        assert not is_stale_session_error(
            mcp_types.ErrorData(code=-32602, message="Invalid params")
        )
