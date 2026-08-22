"""Tests for AgentFactory networked routing + pip_install injection (#56)."""

import uuid
from unittest.mock import MagicMock

import dspy

from canvas_server.runner.agent_factory import AgentFactory


class FakeToolRegistry:
    def get_tools_for_agent(self, agent_id, edges):
        return []


class FakeMemoryManager:
    initialization_error = None

    def needs_memory(self, agent_node):
        return False

    def build_provider(self, agent_node):
        return None


class FakeAgentNode:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid.uuid4())
        self.name = kwargs.get("name", "Worker")
        self.role = kwargs.get("role", "")
        self.instructions = kwargs.get("instructions", "")
        self.model_name = kwargs.get("model_name", "ollama:llama3.1")
        self.agent_type = kwargs.get("agent_type", "worker")
        self.enable_plotting = kwargs.get("enable_plotting", False)
        self.enable_coding = kwargs.get("enable_coding", False)
        self.enable_network = kwargs.get("enable_network", False)
        self.enable_hitl = kwargs.get("enable_hitl", False)
        self.enable_memory = kwargs.get("enable_memory", False)
        self.enable_conversation_history = kwargs.get(
            "enable_conversation_history", False
        )
        self.enable_rag = kwargs.get("enable_rag", False)


def _make_factory(conversation_id="conv-1") -> AgentFactory:
    lm = MagicMock(spec=dspy.LM)
    return AgentFactory(
        lm=lm,
        tool_registry=FakeToolRegistry(),
        memory_manager=FakeMemoryManager(),
        edges=[],
        agent_names={},
        conversation_id=conversation_id,
        conversation_repo=MagicMock(),
    )


class TestBuildWorkerNetworkRouting:
    async def test_networked_worker_gets_pip_install_tool(self):
        factory = _make_factory()
        node = FakeAgentNode(name="NetWorker", enable_network=True)

        agent = await factory.build_worker(node)

        assert "pip_install" in agent.tools

    async def test_non_networked_worker_has_no_pip_install(self):
        factory = _make_factory()
        node = FakeAgentNode(name="Worker")

        agent = await factory.build_worker(node)

        assert "pip_install" not in agent.tools

    async def test_networked_worker_run_code_uses_networked_pool(self):
        """A worker with both coding + network runs run_code in the networked
        pool so pip-installed packages are importable from run_code."""
        with patch_code_provider() as mock_provider_cls:
            factory = _make_factory()
            node = FakeAgentNode(name="Coder", enable_coding=True, enable_network=True)

            await factory.build_worker(node)

        # The CodeProvider was constructed with the networked pool.
        assert mock_provider_cls.call_args.kwargs["network_pool"] == "networked"

    async def test_coding_only_worker_run_code_uses_default_pool(self):
        """A coding worker without network stays on the locked (default) pool."""
        with patch_code_provider() as mock_provider_cls:
            factory = _make_factory()
            node = FakeAgentNode(name="Coder", enable_coding=True)

            await factory.build_worker(node)

        assert mock_provider_cls.call_args.kwargs["network_pool"] == "default"

    async def test_network_only_worker_still_constructs_provider(self):
        """enable_network without enable_coding still constructs a CodeProvider
        (for pip_install) on the networked pool."""
        with patch_code_provider() as mock_provider_cls:
            factory = _make_factory()
            node = FakeAgentNode(name="NetWorker", enable_network=True)

            await factory.build_worker(node)

        assert mock_provider_cls.call_args.kwargs["network_pool"] == "networked"

    async def test_neither_coding_nor_network_constructs_no_provider(self):
        with patch_code_provider() as mock_provider_cls:
            factory = _make_factory()
            node = FakeAgentNode(name="Worker")

            await factory.build_worker(node)

        mock_provider_cls.assert_not_called()


class TestBuildWorkerNetworkPrompt:
    async def test_networked_agent_prompt_has_pip_install_rule(self):
        factory = _make_factory()
        node = FakeAgentNode(name="NetWorker", enable_network=True)

        agent = await factory.build_worker(node)

        instructions = agent.react.signature.instructions
        assert "pip_install" in instructions
        assert "unfamiliar" in instructions.lower()

    async def test_non_networked_agent_prompt_has_no_pip_install_rule(self):
        factory = _make_factory()
        node = FakeAgentNode(name="Worker", enable_coding=True)

        agent = await factory.build_worker(node)

        instructions = agent.react.signature.instructions
        assert "pip_install" not in instructions

    async def test_network_only_prompt_does_not_reference_run_code(self):
        """A network-only worker (network without coding) has pip_install but
        NOT run_code, so its prompt rule must not tell it to use run_code (#56
        spec-axis review: the rule referenced a tool the agent lacks)."""
        factory = _make_factory()
        node = FakeAgentNode(name="NetOnly", enable_network=True, enable_coding=False)

        agent = await factory.build_worker(node)

        instructions = agent.react.signature.instructions
        assert "pip_install" in instructions
        assert "run_code" not in instructions

    async def test_network_and_coding_prompt_references_run_code(self):
        """When both network and coding are on, the agent does have run_code, so
        the prompt rule may reference it for importing installed packages."""
        factory = _make_factory()
        node = FakeAgentNode(
            name="NetCoder", enable_network=True, enable_coding=True
        )

        agent = await factory.build_worker(node)

        instructions = agent.react.signature.instructions
        assert "pip_install" in instructions
        assert "run_code" in instructions


class TestBuildRouterNoPipInstall:
    async def test_router_never_gets_pip_install(self):
        """Routers never get network sessions or pip_install (#56)."""
        from canvas_server.runner.handoff import HandoffToolBuilder

        factory = _make_factory()
        router = FakeAgentNode(name="Router", agent_type="router")
        worker = FakeAgentNode(name="Worker", agent_type="worker")

        async def _fake_targets(_aid):
            return [worker.id]

        factory._get_handoff_target_ids = _fake_targets

        async def _handoff_tool(task: str) -> str:  # noqa: D401
            """Transfer to a downstream agent."""
            return ""

        async def _parallel_tool(payload):  # noqa: D401
            """Run downstream agents in parallel."""
            return ""

        handoff_builder = MagicMock(spec=HandoffToolBuilder)
        handoff_builder.make_handoff_tool.return_value = _handoff_tool
        handoff_builder.make_parallel_handoff_tool.return_value = _parallel_tool

        agent = await factory.build_router(
            router,
            existing_agents={},
            router_name="Router",
            send_event=MagicMock(),
            history_text="",
            dspy_history=None,
            handoff_tool_builder=handoff_builder,
        )

        assert "pip_install" not in agent.tools
        assert "run_code" not in agent.tools


# ── helper ──


def patch_code_provider():
    """Patch CodeProvider so its constructor ``network_pool`` kwarg can be
    inspected, while still returning a *real* CodeProvider whose async methods
    (proper signatures) DSPy can toolify. The patch mock's ``call_args`` records
    the construction kwargs."""
    from unittest.mock import patch

    from canvas_server.runner.code_provider import CodeProvider as _RealCodeProvider

    def _capture(*args, **kwargs):
        return _RealCodeProvider(*args, **kwargs)

    return patch(
        "canvas_server.runner.agent_factory.CodeProvider", side_effect=_capture
    )
