"""PackageManager service for managing Python packages in the Docker sandbox.

This service provides utility methods to validate and clean Python package names.
Actual installation is handled by the sandbox session via the `libraries` argument.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("canvas_server.package_manager")


class PackageManager:
    """Service for validating and cleaning Python package requirements."""

    async def install_packages(self, packages: list[str]) -> None:
        """Installs the specified Python packages in the global sandbox session.

        Args:
            packages: A list of package names to install.
        """
        cleaned_packages = self.validate_packages(packages)
        if not cleaned_packages:
            logger.info("No valid packages to install.")
            return

        from canvas_server.sandbox import get_sandbox
        manager = await get_sandbox()
        session = manager.get_session("syntax_check_global")
        try:
            logger.info(f"Installing packages in sandbox: {cleaned_packages}")
            with session:
                result = session.execute_command("pip install " + " ".join(cleaned_packages))
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

