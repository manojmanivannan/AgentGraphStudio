"""PackageManager service for managing Python packages in the Docker sandbox.

This service provides utility methods to validate and clean Python package names.
Actual installation is handled by the sandbox session via the `libraries` argument.
"""

from __future__ import annotations

import logging

from canvas_server.pip_hardening import build_pip_install_command
from canvas_server.sandbox import get_sandbox

logger = logging.getLogger("canvas_server.package_manager")


class PackageManager:
    """Service for validating and cleaning Python package requirements."""

    async def install_packages(
        self,
        packages: list[str],
        runtime_session_id: str | None = None,
    ) -> None:
        """Installs the specified Python packages in the sandbox session.

        Uses the shared hardened command builder (#56): PEP 508 validation,
        flag rejection, ``shlex.quote`` per token, ≤ 20 packages. A bad token
        raises ``ValueError`` before the sandbox is touched.

        Args:
            packages: A list of package names to install.
            runtime_session_id: Optional conversation-scoped session ID.
                Falls back to the global syntax-check session when omitted.
        """
        cleaned_packages = self.validate_packages(packages)
        if not cleaned_packages:
            logger.info("No valid packages to install.")
            return

        # Build the hardened command up front — a bad token / over-limit batch
        # raises ValueError before any sandbox call.
        command = build_pip_install_command(cleaned_packages)

        manager = await get_sandbox()
        session_id = runtime_session_id or "syntax_check_global"
        session = manager.get_session(session_id, enable_plotting=False)
        try:
            logger.info(f"Installing packages in sandbox: {cleaned_packages}")
            with session:
                result = session.execute_command(command)
                if result.exit_code != 0:
                    raise Exception(result.stderr or result.stdout)
            logger.info("Packages installed successfully.")
        except Exception as e:
            logger.error(f"Failed to install packages in sandbox: {e}")
            raise e

    def validate_packages(self, packages: list[str] | None) -> list[str]:
        """
        Cleans and validates a list of package strings.

        Args:
            packages: The raw list of package strings (can be None).

        Returns:
            A list of non-empty, stripped package names.
        """
        if not packages:
            return []

        return [p.strip() for p in packages if p and p.strip()]

