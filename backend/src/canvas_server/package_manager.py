"""PackageManager service for managing Python packages in the Deno/Pyodide sandbox.

This service provides utility methods to install and validate Python packages
in the isolated Pyodide environment.  Packages are loaded by triggering Pyodide's
built-in ``loadPackagesFromImports`` which downloads packages from the CDN.
"""

from __future__ import annotations

import logging
from canvas_server.sandbox import Sandbox


logger = logging.getLogger("canvas_server.package_manager")


class PackageManager:
    """Service for managing Python packages within the sandbox."""

    async def install_packages(self, packages: list[str]) -> None:
        """Loads the specified Python packages in the sandbox.

        Works by sending code that imports the requested packages — this
        triggers Pyodide's ``loadPackagesFromImports`` which auto-downloads
        them from the CDN.

        Args:
            packages: A list of package names to install (e.g., ["numpy", "pandas"]).
        """
        cleaned_packages = self.validate_packages(packages)
        if not cleaned_packages:
            logger.info("No valid packages to install.")
            return

        sandbox = await Sandbox.get()

        # Generate import statements for each package.  The sandbox runner's
        # loadPackagesFromImports will detect these and auto-download them.
        import_stmts = "\n".join(f"import {pkg}" for pkg in cleaned_packages)
        # End with a sentinel so the sandbox returns something meaningful.
        snippet = import_stmts + '\n"ok"'

        try:
            logger.info(f"Installing packages in sandbox: {cleaned_packages}")
            sandbox(snippet)
            logger.info("Packages installed successfully.")
        except Exception as e:
            logger.error(f"Failed to install packages in sandbox: {e}")
            raise e

    def validate_packages(self, packages: list[str]) -> list[str]:
        """
        Cleans and validates a list of package strings.

        Args:
            packages: The raw list of package strings.

        Returns:
            A list of non-empty, stripped package names.
        """
        if not packages:
            return []

        return [p.strip() for p in packages if p and p.strip()]
