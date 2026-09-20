import uuid
from unittest.mock import ANY, AsyncMock, MagicMock, mock_open, patch

import pytest
from llm_sandbox.data import ExecutionResult, FileType, PlotOutput

from canvas_server.runner.plot_provider import PlotProvider


@pytest.mark.asyncio
async def test_plot_provider_success():
    """Test plot generation successfully saves files and returns markdown links."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_result = ExecutionResult(
        exit_code=0,
        stdout="Plot generated",
        stderr="",
        plots=[mock_plot]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox, \
         patch("builtins.open", mock_open()) as mock_file, \
         patch("os.makedirs") as mock_makedirs:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result_str = await provider.generate_plot("import matplotlib.pyplot as plt; plt.show()")

        mock_get_sandbox.assert_called_once()
        mock_sandbox_manager.get_session.assert_called_once_with("test_conv_id", enable_plotting=True)
        mock_session.__enter__.assert_called_once()
        mock_session.run.assert_called_once_with("import matplotlib.pyplot as plt; plt.show()")
        mock_session.__exit__.assert_called_once()

        mock_makedirs.assert_called_once()
        mock_file.assert_called_once()

        assert "Plot generated" in result_str
        assert "![Plot](/api/static/plots/" in result_str
        assert ".png" in result_str


@pytest.mark.asyncio
async def test_plot_provider_failure():
    """Test exit code failure returns a proper error message with stderr."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_result = ExecutionResult(
        exit_code=1,
        stdout="",
        stderr="SyntaxError: invalid syntax",
        plots=[]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("invalid python code")

        assert "Error executing plot code (exit code 1)" in result
        assert "SyntaxError: invalid syntax" in result


@pytest.mark.asyncio
async def test_plot_provider_no_plots():
    """Test execution succeeds but no plots are generated warns the user."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_result = ExecutionResult(
        exit_code=0,
        stdout="print('hello')",
        stderr="",
        plots=[]
    )
    mock_session.run.return_value = mock_result

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("print('hello')")

        assert "no plots were generated" in result
        assert "print('hello')" in result


@pytest.mark.asyncio
async def test_plot_provider_exception():
    """Test exception during sandbox acquisition or run is caught gracefully."""
    with patch("canvas_server.runner.plot_provider.get_sandbox", side_effect=Exception("Connection failed")):
        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("plt.show()")

        assert "Error generating plot: Connection failed" in result


@pytest.mark.asyncio
async def test_plot_provider_success_db():
    """Test plot generation successfully saves to database when conversation_repo is provided."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_result = ExecutionResult(
        exit_code=0,
        stdout="Plot generated",
        stderr="",
        plots=[mock_plot]
    )
    mock_session.run.return_value = mock_result

    mock_repo = AsyncMock()
    mock_record = MagicMock()
    mock_record.id = "mocked-plot-uuid"
    mock_repo.save_attachment.return_value = mock_record

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="8cf53a28-98cc-4d37-88eb-116dbec8e2cb", conversation_repo=mock_repo)
        result_str = await provider.generate_plot("import matplotlib.pyplot as plt; plt.show()")

        mock_get_sandbox.assert_called_once()
        mock_sandbox_manager.get_session.assert_called_once_with("8cf53a28-98cc-4d37-88eb-116dbec8e2cb", enable_plotting=True)
        mock_session.__enter__.assert_called_once()
        mock_session.run.assert_called_once_with("import matplotlib.pyplot as plt; plt.show()")
        mock_session.__exit__.assert_called_once()

        mock_repo.save_attachment.assert_called_once_with(
            conversation_id=uuid.UUID("8cf53a28-98cc-4d37-88eb-116dbec8e2cb"),
            content=b"mock_base64_data",
            format="png",
            file_type="image",
            source="agent_output",
            produced_by_run_id=None,
            original_filename=ANY,
        )
        filename = mock_repo.save_attachment.await_args.kwargs["original_filename"]
        assert filename.startswith("plot_")
        assert filename.endswith(".png")
        assert len(filename.removeprefix("plot_").removesuffix(".png")) == 32
        # #87: the tool no longer embeds a markdown link for the LLM to copy
        # — the plot is announced via the unified `attachment_produced` event
        # instead, so the return value stays a plain confirmation string.
        assert "Plot generated" in result_str
        assert "![Plot]" not in result_str
        assert "attached" in result_str.lower()


@pytest.mark.asyncio
async def test_plot_provider_fires_attachment_produced_event_and_persists_message():
    """#87: the plot becomes an `image`-typed AttachmentInstance (source
    `agent_output`) going through the same storage call used by #86's
    output-extraction mechanism, and its production fires the same
    `attachment_produced` event/persisted message — not a separate/duplicate
    code path."""
    from types import SimpleNamespace

    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_session.run.return_value = ExecutionResult(
        exit_code=0, stdout="Plot generated", stderr="", plots=[mock_plot]
    )

    mock_repo = AsyncMock()
    stored_attachment_id = uuid.uuid4()
    mock_repo.save_attachment.return_value = MagicMock(id=stored_attachment_id)

    agent_id = uuid.uuid4()
    run_id = uuid.uuid4()
    send_event = AsyncMock()
    conversation_service = AsyncMock()
    run_state = SimpleNamespace(
        send_event=send_event,
        conversation_service=conversation_service,
        run_id=run_id,
    )

    conversation_id = uuid.uuid4()

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(
            conversation_id=conversation_id,
            conversation_repo=mock_repo,
            agent_id=agent_id,
            agent_name="Plotter",
            run_state=run_state,
        )
        await provider.generate_plot("import matplotlib.pyplot as plt; plt.show()")

    mock_repo.save_attachment.assert_called_once_with(
        conversation_id=conversation_id,
        content=b"mock_base64_data",
        format="png",
        file_type="image",
        source="agent_output",
        produced_by_run_id=run_id,
        original_filename=ANY,
    )

    send_event.assert_awaited_once()
    payload = send_event.await_args.args[0]
    assert payload["type"] == "attachment_produced"
    assert payload["attachment_id"] == str(stored_attachment_id)
    assert payload["file_type"] == "image"
    assert payload["source"] == "agent_output"
    assert payload["agent"] == "Plotter"
    assert payload["node_id"] == str(agent_id)
    assert payload["run_id"] == str(run_id)
    assert payload["original_filename"] == mock_repo.save_attachment.await_args.kwargs[
        "original_filename"
    ]
    assert payload["conversation_id"] == str(conversation_id)

    conversation_service.persist_message.assert_awaited_once()
    persist_kwargs = conversation_service.persist_message.await_args.kwargs
    assert persist_kwargs["event_type"] == "attachment_produced"
    assert persist_kwargs["args"]["attachment_id"] == str(stored_attachment_id)


@pytest.mark.asyncio
async def test_plot_provider_multiple_plots_get_distinct_names():
    """Multiple plots produced by a single `generate_plot` call each get a
    distinct, stable name in their `attachment_produced` announcement."""
    from types import SimpleNamespace

    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    plot_a = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    plot_b = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_session.run.return_value = ExecutionResult(
        exit_code=0, stdout="", stderr="", plots=[plot_a, plot_b]
    )

    mock_repo = AsyncMock()
    mock_repo.save_attachment.side_effect = [
        MagicMock(id=uuid.uuid4()),
        MagicMock(id=uuid.uuid4()),
    ]

    send_event = AsyncMock()
    run_state = SimpleNamespace(
        send_event=send_event,
        conversation_service=AsyncMock(),
        run_id=None,
    )

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(
            conversation_id=uuid.uuid4(),
            conversation_repo=mock_repo,
            agent_id=uuid.uuid4(),
            agent_name="Plotter",
            run_state=run_state,
        )
        await provider.generate_plot("plt.show(); plt.show()")

    assert send_event.await_count == 2
    names = [c.args[0]["name"] for c in send_event.await_args_list]
    assert len(set(names)) == 2


@pytest.mark.asyncio
async def test_plot_provider_without_run_state_skips_event_but_still_stores():
    """Missing agent context (e.g. unit-tests constructing PlotProvider
    directly) must never raise — storage still happens, announcement is
    simply skipped."""
    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session

    mock_plot = PlotOutput(format=FileType.PNG, content_base64="bW9ja19iYXNlNjRfZGF0YQ==")
    mock_session.run.return_value = ExecutionResult(
        exit_code=0, stdout="", stderr="", plots=[mock_plot]
    )

    mock_repo = AsyncMock()
    mock_repo.save_attachment.return_value = MagicMock(id=uuid.uuid4())

    with patch("canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id=uuid.uuid4(), conversation_repo=mock_repo)
        result_str = await provider.generate_plot("plt.show()")

    mock_repo.save_attachment.assert_called_once()
    assert "attached" in result_str.lower()


@pytest.mark.asyncio
async def test_plot_provider_pool_busy_returns_observation():
    """Under parallel handoffs a saturated pool must surface as the bounded
    'busy' observation — never a raw PoolExhaustedError after the pool's 30s
    WAIT strategy ('Error generating plot: All 2 containers in pool are busy
    and timeout of 30.0s exceeded')."""
    from llm_sandbox.pool import PoolExhaustedError

    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()
    mock_sandbox_manager.get_session.return_value = mock_session
    mock_session.__enter__.side_effect = PoolExhaustedError(2, 30.0)

    with patch(
        "canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock
    ) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        result = await provider.generate_plot("import matplotlib.pyplot as plt")

        assert "Code sandbox busy" in result
        mock_session.run.assert_not_called()


@pytest.mark.asyncio
async def test_plot_provider_does_not_block_event_loop():
    """The blocking sandbox calls run in a worker thread: while a slow plot
    execution is in flight, other tasks on the event loop keep running. Before
    the fix, ``generate_plot`` ran ``with session:`` / ``session.run`` directly
    on the loop, freezing all parallel agents and WebSocket streaming."""
    import asyncio

    mock_sandbox_manager = MagicMock()
    mock_session = MagicMock()

    running = asyncio.Event()
    loop = asyncio.get_running_loop()

    def slow_run(code, **kwargs):
        # asyncio.Event is not thread-safe: signal the loop via
        # call_soon_threadsafe or the waiter may not wake until the
        # worker thread finishes.
        loop.call_soon_threadsafe(running.set)  # the blocking call is in flight
        import time

        time.sleep(0.3)
        return ExecutionResult(exit_code=0, stdout="", stderr="", plots=[])

    mock_session.run.side_effect = slow_run
    mock_sandbox_manager.get_session.return_value = mock_session

    with patch(
        "canvas_server.runner.plot_provider.get_sandbox", new_callable=AsyncMock
    ) as mock_get_sandbox:
        mock_get_sandbox.return_value = mock_sandbox_manager

        provider = PlotProvider(conversation_id="test_conv_id")
        plot_task = asyncio.create_task(provider.generate_plot("plt.show()"))

        # Wait until the blocking run has started, then confirm the event loop
        # stayed responsive while it was still in flight.
        await asyncio.wait_for(running.wait(), timeout=2.0)
        loop_alive_marker = asyncio.Event()
        await asyncio.wait_for(asyncio.sleep(0.05), timeout=1.0)
        loop_alive_marker.set()  # only reachable if the loop was never blocked

        result = await asyncio.wait_for(plot_task, timeout=5.0)
        assert "no plots were generated" in result


def test_canvas_sandbox_session_enable_plotting_sync():
    """Verify CanvasSandboxSession's enable_plotting property keeps _pooled_impl in sync."""
    from canvas_server.sandbox import CanvasSandboxSession

    class FakeDockerPool:
        lang = "python"
        image = "image"
        client = MagicMock()
        runtime_configs = {}
        session_kwargs = {}

    session = CanvasSandboxSession(pool=FakeDockerPool(), enable_plotting=False)

    assert session.enable_plotting is False
    assert session._pooled_impl.enable_plotting is False

    session.enable_plotting = True
    assert session.enable_plotting is True
    assert session._pooled_impl.enable_plotting is True

    session.enable_plotting = False
    assert session.enable_plotting is False
    assert session._pooled_impl.enable_plotting is False


def test_sandbox_manager_session_reuse_switches_enable_plotting():
    """Verify that when SandboxManager reuses an existing session for a conversation,
    setting enable_plotting=True properly updates the session so plotting works."""
    from canvas_server.sandbox import SandboxManager

    class FakeDockerPool:
        lang = "python"
        image = "image"
        client = MagicMock()
        runtime_configs = {}
        session_kwargs = {}

    mgr = SandboxManager()
    mgr._locked_pool = FakeDockerPool()
    mgr._initialized = True

    # 1. First tool (e.g. get_weather_forecast or run_code) acquires session with enable_plotting=False
    session1 = mgr.get_session("conv-123", enable_plotting=False)
    assert session1.enable_plotting is False
    assert session1._pooled_impl.enable_plotting is False

    # 2. Next tool (generate_plot) acquires the same session with enable_plotting=True
    session2 = mgr.get_session("conv-123", enable_plotting=True)
    assert session2 is session1
    assert session2.enable_plotting is True
    assert session2._pooled_impl.enable_plotting is True

