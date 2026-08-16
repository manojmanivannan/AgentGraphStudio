import asyncio
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_sandbox.data import ExecutionResult
from llm_sandbox.exceptions import SandboxTimeoutError
from llm_sandbox.pool import PoolExhaustedError

from canvas_server.runner.code_provider import CodeProvider

requires_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="Docker not installed"
)


def _result(exit_code=0, stdout="", stderr=""):
    return ExecutionResult(exit_code=exit_code, stdout=stdout, stderr=stderr, plots=[])


def _patch_sandbox(mock_sandbox):
    """Patch get_sandbox to an AsyncMock whose return value is a plain MagicMock."""
    gs = AsyncMock()
    gs.return_value = mock_sandbox
    return patch("canvas_server.runner.code_provider.get_sandbox", new=gs)


@pytest.mark.asyncio
async def test_code_provider_success():
    """exit 0 -> stdout returned verbatim as a text observation."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(stdout="42\n")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print(40 + 2)")

    # network_pool="default" routes to the locked (non-networked) pool (#55).
    mock_sandbox.get_session.assert_called_once_with(
        "conv-1", enable_plotting=False, network_pool="default"
    )
    mock_session.__enter__.assert_called_once()
    mock_session.__exit__.assert_called_once()
    mock_session.run.assert_called_once()
    assert mock_session.run.call_args.args[0] == "print(40 + 2)"
    assert mock_session.run.call_args.kwargs.get("timeout") == 60
    assert result == "42\n"


@pytest.mark.asyncio
async def test_code_provider_nonzero_exit_keeps_partial_stdout():
    """non-zero exit -> partial stdout preserved, stderr appended as error block."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(
        exit_code=1, stdout="partial output\n", stderr="NameError: x is not defined"
    )

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print(x)")

    assert "partial output" in result
    assert "Error executing code (exit code 1)" in result
    assert "NameError: x is not defined" in result


@pytest.mark.asyncio
async def test_code_provider_nonzero_exit_no_stdout():
    """non-zero exit with no stdout -> just the error block (no leading blank line)."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(exit_code=2, stdout="", stderr="boom")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("raise SystemExit(2)")

    assert result == "Error executing code (exit code 2):\nboom"


@pytest.mark.asyncio
async def test_code_provider_truncation():
    """stdout beyond 8000 chars is dropped with the documented marker."""
    big = "x" * 20_000
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(stdout=big)

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print('x' * 20000)")

    assert "…[truncated at 8000 chars — narrow your print, or save to a file and read a slice]" in result
    assert len(result) < 20_000
    # The kept portion is exactly the first 8000 chars.
    assert result.startswith("x" * 8000)


@pytest.mark.asyncio
async def test_code_provider_truncation_error_path_single_cap():
    """On the error path the combined observation is capped once at 8000 with one marker."""
    big_stdout = "s" * 20_000
    big_stderr = "e" * 20_000
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(exit_code=1, stdout=big_stdout, stderr=big_stderr)

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print('s' * 20000); raise ValueError('e' * 20000)")

    # Exactly one truncation marker, not one per stream.
    assert result.count("…[truncated at 8000 chars — narrow your print, or save to a file and read a slice]") == 1
    # The whole observation is bounded by the single 8000-char cap (+ marker).
    assert len(result) < 20_000
    # Partial stdout is preserved at the front of the capped observation.
    assert result.startswith("s" * 8000)


@pytest.mark.asyncio
async def test_code_provider_enable_plotting_false():
    """run_code never enables plot detection — get_session called with enable_plotting=False."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(stdout="ok")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print('ok')")

    assert mock_sandbox.get_session.call_args.kwargs["enable_plotting"] is False
    assert result == "ok"


@pytest.mark.asyncio
async def test_code_provider_timeout():
    """A SandboxTimeoutError from session.run becomes a descriptive observation, never raised."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.side_effect = SandboxTimeoutError("timed out")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("while True: pass")

    assert "timed out" in result.lower() or "timeout" in result.lower()
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_code_provider_pool_exhausted():
    """PoolExhaustedError on session acquire -> bounded-wait 'busy' observation."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.__enter__.side_effect = PoolExhaustedError("no containers")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print('hi')")

    assert "busy" in result.lower()


@pytest.mark.asyncio
async def test_code_provider_bounded_wait_timeout(monkeypatch):
    """An acquire that blocks longer than the bound returns the 'busy' observation."""
    monkeypatch.setattr("canvas_server.runner.code_provider.ACQUIRE_TIMEOUT", 0.1)

    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session

    def slow_enter():
        # Simulate a blocking pool acquire that exceeds the bound.
        import time
        time.sleep(0.3)

    mock_session.__enter__.side_effect = slow_enter

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        result = await asyncio.wait_for(provider.run_code("print('hi')"), timeout=5)

    assert "busy" in result.lower()
    # Let the orphaned acquire + its cleanup task finish so no task is left pending.
    await asyncio.sleep(0.4)
    mock_session.__exit__.assert_called_once()


@pytest.mark.asyncio
async def test_code_provider_never_raises():
    """Any unexpected internal error is caught and returned as an 'Error: …' observation."""
    with patch("canvas_server.runner.code_provider.get_sandbox", new_callable=AsyncMock) as gs:
        gs.side_effect = RuntimeError("sandbox blew up")
        provider = CodeProvider(conversation_id="conv-1")
        result = await provider.run_code("print('hi')")

    assert result.startswith("Error")
    assert "sandbox blew up" in result


@pytest.mark.asyncio
async def test_code_provider_session_exited_on_success():
    """The sandbox session is released (context exited) after a successful run."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.return_value = _result(stdout="ok")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        await provider.run_code("print('ok')")

    mock_session.__exit__.assert_called_once()


@pytest.mark.asyncio
async def test_code_provider_session_exited_on_run_error():
    """The sandbox session is released even when session.run raises."""
    mock_sandbox = MagicMock()
    mock_session = MagicMock()
    mock_sandbox.get_session.return_value = mock_session
    mock_session.run.side_effect = SandboxTimeoutError("timed out")

    with _patch_sandbox(mock_sandbox):
        provider = CodeProvider(conversation_id="conv-1")
        await provider.run_code("while True: pass")

    mock_session.__exit__.assert_called_once()


@requires_docker
@pytest.mark.asyncio
async def test_code_provider_real_execution():
    """run_code actually executes Python in Docker and returns stdout (no mocks)."""
    provider = CodeProvider(conversation_id="test-code-real-exec")

    # Tolerate cold-start pool warmup: the first acquire may exceed the 10s
    # bounded wait while the pool's containers warm up, surfacing as 'busy'.
    # Retry until the pool is ready, then assert real execution.
    result = ""
    for _ in range(8):
        result = await provider.run_code("print(6 * 7)")
        if "busy" not in result.lower():
            break
        await asyncio.sleep(2)
    assert result.strip() == "42"

    # Files persist across run_code calls within the turn's pinned container
    # (#55 per-turn container pinning): a file written in the workdir here is
    # readable in the next call — this is the run_code -> generate_plot handoff
    # mechanism, and it only works because the container is held for the whole
    # turn and the workdir is cleaned once (on first acquire), not per call.
    await provider.run_code("open('/sandbox/ags_handoff.txt', 'w').write('21')")
    result2 = await provider.run_code("print(open('/sandbox/ags_handoff.txt').read())")
    assert result2.strip() == "21"

    # Failures surface as observations instead of raising.
    result3 = await provider.run_code("print(undefined_name)")
    assert "Error executing code" in result3

    # Release the turn's pinned container so the test does not leak it.
    from canvas_server.sandbox import get_sandbox

    sandbox = await get_sandbox()
    sandbox.release_session("test-code-real-exec")
