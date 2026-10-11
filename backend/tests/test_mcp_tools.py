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

        assert observation == "3"
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
    50k cap with truncation note; isError never raises."""

    def test_single_text_block_is_a_plain_string(self):
        observation, raw = format_mcp_result(text_result("3"))
        assert observation == "3"
        assert raw[0]["type"] == "text" and raw[0]["text"] == "3"

    def test_multiple_text_blocks_are_joined_with_newlines(self):
        observation, _ = format_mcp_result(text_result("t1", "t2", "t3"))
        assert observation == "t1\nt2\nt3"

    def test_non_text_blocks_become_a_placeholder_note(self):
        observation, _ = format_mcp_result(mixed_result())
        assert observation == "t1\nt2\nt3\n[1 image block returned, 3 text blocks]"

    def test_non_text_only_results_are_all_note(self):
        observation, _ = format_mcp_result(
            mcp_types.CallToolResult(content=[image_block()])
        )
        assert observation == "[1 image block returned]"

    def test_multiple_non_text_counts_summarized_per_type(self):
        observation, _ = format_mcp_result(
            mcp_types.CallToolResult(
                content=[image_block(), image_block(), audio_block()]
            )
        )
        assert observation == "[2 image blocks returned, 1 audio block returned]"

    def test_empty_result_observes_placeholder(self):
        observation, raw = format_mcp_result(mcp_types.CallToolResult(content=[]))
        assert observation == "" and raw == []

    async def test_is_error_is_an_ordinary_observation(self):
        # dspy 3.4.0's convert_mcp_tool raises RuntimeError for isError — the
        # framed observation must never raise, run continues (spec §4.5).
        session = RecordingSession(text_result("ValueError: boom", is_error=True))
        tool = make_descriptor(session)
        observation = await tool.acall(a=1, b=2)
        assert observation == "ValueError: boom"

    async def test_big_output_is_capped_with_truncation_note(self):
        session = RecordingSession(text_result("A" * 60_000))
        tool = make_descriptor(session)
        observation = await tool.acall(a=1, b=2)

        assert observation.startswith("A" * MCP_RESULT_MAX_CHARS)
        assert "truncated" in observation
        assert len(observation) <= MCP_RESULT_MAX_CHARS + 100

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
