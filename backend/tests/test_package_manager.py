from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_server.package_manager import PackageManager


class TestPackageManager:
    async def test_install_packages_uses_runtime_session_id_when_provided(self):
        pm = PackageManager()

        manager = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        session.execute_command.return_value = MagicMock(
            exit_code=0,
            stdout="ok",
            stderr="",
        )
        manager.get_session.return_value = session

        with patch(
            "canvas_server.package_manager.get_sandbox",
            new=AsyncMock(return_value=manager),
        ):
            await pm.install_packages(["numpy", "pandas"], runtime_session_id="conversation-7")

        manager.get_session.assert_called_once_with(
            "conversation-7",
            enable_plotting=False,
        )
        # Hardened command (shared builder) — tokens quoted (#56).
        cmd = session.execute_command.call_args.args[0]
        assert cmd == "pip install numpy pandas"

    async def test_install_packages_defaults_to_global_session(self):
        pm = PackageManager()

        manager = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        session.execute_command.return_value = MagicMock(
            exit_code=0,
            stdout="ok",
            stderr="",
        )
        manager.get_session.return_value = session

        with patch(
            "canvas_server.package_manager.get_sandbox",
            new=AsyncMock(return_value=manager),
        ):
            await pm.install_packages(["requests"])

        manager.get_session.assert_called_once_with(
            "syntax_check_global",
            enable_plotting=False,
        )

    async def test_install_packages_quotes_specifier_tokens(self):
        """Author-tool dependency install uses the shared hardened builder, so
        PEP 508 specifier tokens are shell-quoted (#56)."""
        pm = PackageManager()

        manager = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        session.execute_command.return_value = MagicMock(
            exit_code=0, stdout="ok", stderr=""
        )
        manager.get_session.return_value = session

        with patch(
            "canvas_server.package_manager.get_sandbox",
            new=AsyncMock(return_value=manager),
        ):
            await pm.install_packages(["numpy>=1.26"])

        assert session.execute_command.call_args.args[0] == "pip install 'numpy>=1.26'"

    async def test_install_packages_rejects_bad_token_before_execute(self):
        """A flag-like dependency token is rejected by the hardened builder
        before the sandbox is touched — raises, execute_command not called (#56)."""
        pm = PackageManager()

        manager = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = session
        session.__exit__.return_value = None
        manager.get_session.return_value = session

        with patch(
            "canvas_server.package_manager.get_sandbox",
            new=AsyncMock(return_value=manager),
        ), pytest.raises(ValueError):
            await pm.install_packages(["--index-url=http://evil", "requests"])

        session.execute_command.assert_not_called()
