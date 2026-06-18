from unittest.mock import AsyncMock, MagicMock, patch

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
