"""PackageManager service for managing Python packages in the Docker sandbox.

This service provides utility methods to validate and clean Python package names.
Actual installation is handled by the sandbox session via the `libraries` argument.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("canvas_server.package_manager")


class PackageManager:
    """Service for validating and cleaning Python package requirements."""

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
