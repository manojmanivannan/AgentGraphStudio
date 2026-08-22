"""Shared hardening for ``pip install`` invocations (#56).

Both the agent-facing ``pip_install`` tool (``CodeProvider``) and the
author-facing dependency-install paths (``tool_factory`` /
``package_manager``) build the ``pip install`` command through this module so
the hardening rules live in one place.

Rules (issue #56):
- **PEP 508 validate each token** — a token that is not a valid PEP 508
  requirement (e.g. ``--index-url=http://evil`` or ``not a valid package!``)
  rejects the *whole* install. No partial install.
- **Reject flag-like tokens** — any token starting with ``-`` is rejected
  outright (defensive cover for ``--index-url`` / ``--trusted-host`` /
  ``--no-deps`` and any future pip option). Default PyPI only.
- **``shlex.quote`` each token** — the command is interpolated into an
  ``execute_command`` shell string, so each token is shell-escaped to prevent
  injection.
- **≤ ``MAX_PACKAGES`` packages per call** — a cap on a single install.
- **Typosquat risk accepted** — there is no package allowlist; PEP 508
  validation, flag rejection, quoting, and the count cap are the only guards.

This module is pure (no sandbox / network access) so it unit-tests without
Docker.
"""

from __future__ import annotations

import shlex

from packaging.requirements import InvalidRequirement, Requirement

# Hard cap on packages accepted in a single pip_install call.
MAX_PACKAGES = 20


def validate_pip_tokens(packages: list[str] | None) -> list[str]:
    """Validate and shell-quote a list of pip package requirement tokens.

    Each non-empty, stripped token must be a valid PEP 508 requirement and must
    not start with ``-`` (rejects pip flags). Valid tokens are ``shlex.quote``'d
    so they are safe to interpolate into an ``execute_command`` shell string.

    Args:
        packages: Raw package requirement strings (may be ``None`` / empty).

    Returns:
        The list of validated, shell-quoted tokens (in input order, empties
        dropped).

    Raises:
        ValueError: If any token fails PEP 508 validation, is a flag-like
            token (starts with ``-``), or the batch exceeds ``MAX_PACKAGES``.
    """
    if not packages:
        return []

    stripped = [p.strip() for p in packages if p and p.strip()]
    if len(stripped) > MAX_PACKAGES:
        raise ValueError(
            f"pip_install accepts at most {MAX_PACKAGES} packages per call, "
            f"got {len(stripped)}."
        )

    quoted: list[str] = []
    for token in stripped:
        # Reject flag-like tokens (defensive: covers --index-url /
        # --trusted-host / --no-deps and any future pip option). PEP 508 would
        # also reject these, but the explicit check gives a clearer error and
        # guards against any PEP 508 parser leniency.
        if token.startswith("-"):
            raise ValueError(
                f"pip_install rejects flag-like token '{token}' "
                "(default PyPI only; --index-url/--trusted-host/--no-deps are not allowed)."
            )
        try:
            Requirement(token)
        except InvalidRequirement as exc:
            raise ValueError(
                f"pip_install token '{token}' is not a valid PEP 508 requirement: {exc}"
            ) from exc
        quoted.append(shlex.quote(token))
    return quoted


def build_pip_install_command(packages: list[str] | None) -> str:
    """Build a hardened ``pip install <quoted tokens>`` command string.

    Validates the tokens via :func:`validate_pip_tokens` (raising ``ValueError``
    on any bad token / over-limit batch) and joins them into the command. With
    no tokens this returns the bare ``"pip install"`` — callers decide whether
    to run it.

    Raises:
        ValueError: Propagated from :func:`validate_pip_tokens`.
    """
    quoted = validate_pip_tokens(packages)
    if not quoted:
        return "pip install"
    return "pip install " + " ".join(quoted)
