"""Tests for sandbox output auto-capture helpers (#89)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_server.runner.sandbox_output_capture import (
    read_sandbox_file,
    resolve_sandbox_path,
)
from canvas_server.sandbox import SANDBOX_WORKDIR


def _patch_sandbox(mock_sandbox):
    gs = AsyncMock()
    gs.return_value = mock_sandbox
    return patch("canvas_server.runner.sandbox_output_capture.get_sandbox", new=gs)


class TestResolveSandboxPath:
    def test_keeps_absolute_paths(self):
        assert resolve_sandbox_path("/sandbox/reports/final.pdf") == "/sandbox/reports/final.pdf"

    def test_resolves_relative_paths_under_sandbox_workdir(self):
        assert resolve_sandbox_path("reports/final.pdf") == f"{SANDBOX_WORKDIR}/reports/final.pdf"


@pytest.mark.asyncio
class TestReadSandboxFile:
    async def test_returns_bytes_when_copy_from_runtime_succeeds(self):
        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session
        expected = b"final report bytes"

        def _copy_from_runtime(_container_path, local_dest_path):
            with open(local_dest_path, "wb") as handle:
                handle.write(expected)

        mock_session.copy_from_runtime.side_effect = _copy_from_runtime

        async def _run_work(_session, work, *, timeout):
            return True, await work(mock_session)

        with _patch_sandbox(mock_sandbox), patch(
            "canvas_server.runner.sandbox_output_capture.bounded_session_work",
            new=AsyncMock(side_effect=_run_work),
        ):
            content = await read_sandbox_file(
                conversation_id="conv-1",
                network_pool="default",
                path="reports/final.pdf",
            )

        assert content == expected
        mock_sandbox.get_session.assert_called_once_with(
            "conv-1",
            enable_plotting=False,
            network_pool="default",
        )
        mock_session.copy_from_runtime.assert_called_once()
        assert mock_session.copy_from_runtime.call_args.args[0] == f"{SANDBOX_WORKDIR}/reports/final.pdf"

    async def test_returns_none_and_logs_warning_when_copy_raises(self):
        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session
        mock_session.copy_from_runtime.side_effect = FileNotFoundError("missing")

        async def _run_work(_session, work, *, timeout):
            return True, await work(mock_session)

        with _patch_sandbox(mock_sandbox), patch(
            "canvas_server.runner.sandbox_output_capture.bounded_session_work",
            new=AsyncMock(side_effect=_run_work),
        ), patch("canvas_server.runner.sandbox_output_capture.logger.warning") as mock_warning:
                content = await read_sandbox_file(
                    conversation_id=uuid.uuid4(),
                    network_pool="default",
                    path="/sandbox/missing.txt",
                )

        assert content is None
        mock_warning.assert_called_once()
        assert "could not be read from sandbox path" in mock_warning.call_args.args[0]

    async def test_returns_none_when_pool_is_saturated(self):
        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox), patch(
            "canvas_server.runner.sandbox_output_capture.bounded_session_work",
            new=AsyncMock(return_value=(False, "Code sandbox busy")),
        ), patch("canvas_server.runner.sandbox_output_capture.logger.warning") as mock_warning:
                content = await read_sandbox_file(
                    conversation_id="conv-1",
                    network_pool="networked",
                    path="reports/final.pdf",
                )

        assert content is None
        mock_warning.assert_called_once()
        assert "Sandbox busy" in mock_warning.call_args.args[0]
