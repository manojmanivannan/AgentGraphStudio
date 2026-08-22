"""Tests for the shared pip-install hardening (#56).

Hardening rules (issue #56):
- PEP 508 validate each token — reject the *whole* install on a bad token.
- ``shlex.quote`` each token (shell-injection safe when passed to
  ``session.execute_command``).
- ≤ 20 packages per call.
- Default PyPI only — reject ``--index-url`` / ``--trusted-host`` / ``--no-deps``
  (and any other flag-like token starting with ``-``).
- Typosquat risk accepted (no allowlist).
"""

import pytest

from canvas_server.pip_hardening import (
    MAX_PACKAGES,
    build_pip_install_command,
    validate_pip_tokens,
)


class TestValidatePipTokens:
    def test_simple_names_accepted_and_quoted(self):
        assert validate_pip_tokens(["requests", "numpy"]) == ["requests", "numpy"]

    def test_pep508_specifiers_accepted(self):
        # Specifiers like >=, <, ~= are valid PEP 508. Tokens carrying
        # shell-special chars are returned shell-quoted (safe for interpolation
        # into an execute_command string); the quoted form still parses as the
        # original requirement once the shell unwraps it.
        tokens = validate_pip_tokens(["requests>=2.0,<3", "numpy~=1.26"])
        assert tokens == ["'requests>=2.0,<3'", "'numpy~=1.26'"]

    def test_extras_and_markers_accepted(self):
        tokens = validate_pip_tokens(["requests[socks]>=2.0", "uvicorn[standard]"])
        assert tokens == ["'requests[socks]>=2.0'", "'uvicorn[standard]'"]

    def test_strips_whitespace_and_drops_empties(self):
        assert validate_pip_tokens(["  requests  ", "", "  ", "numpy"]) == [
            "requests",
            "numpy",
        ]

    def test_empty_list_returns_empty(self):
        assert validate_pip_tokens([]) == []
        assert validate_pip_tokens(None) == []  # type: ignore[arg-type]

    def test_rejects_index_url_flag(self):
        with pytest.raises(ValueError):
            validate_pip_tokens(["--index-url=http://evil.example/simple"])

    def test_rejects_trusted_host_flag(self):
        with pytest.raises(ValueError):
            validate_pip_tokens(["--trusted-host", "evil.example"])

    def test_rejects_no_deps_flag(self):
        with pytest.raises(ValueError):
            validate_pip_tokens(["--no-deps", "requests"])

    def test_rejects_any_dash_prefixed_token(self):
        # Any flag-like token (starts with '-') is rejected, not just the
        # named forbidden ones — defensive against future pip options.
        with pytest.raises(ValueError):
            validate_pip_tokens(["--extra-index-url=http://evil"])

    def test_rejects_non_pep508_token(self):
        with pytest.raises(ValueError):
            validate_pip_tokens(["not a valid package!"])

    def test_rejects_whole_install_on_one_bad_token(self):
        # One bad token rejects the whole batch — no partial install.
        with pytest.raises(ValueError):
            validate_pip_tokens(["requests", "--index-url=http://evil"])

    def test_rejects_more_than_max_packages(self):
        too_many = [f"pkg{i}" for i in range(MAX_PACKAGES + 1)]
        with pytest.raises(ValueError):
            validate_pip_tokens(too_many)

    def test_accepts_exactly_max_packages(self):
        exactly_max = [f"pkg{i}" for i in range(MAX_PACKAGES)]
        assert len(validate_pip_tokens(exactly_max)) == MAX_PACKAGES

    def test_quotes_shell_metacharacter_token(self):
        # A valid PEP 508 token containing shell-special characters is returned
        # shell-quoted so it is safe to interpolate into an execute_command
        # string. The quoted form is what gets joined into the command.
        quoted = validate_pip_tokens(["requests>=2.0"])
        # shlex.quote wraps tokens containing shell-special chars in single quotes.
        assert quoted == ["'requests>=2.0'"]


class TestBuildPipInstallCommand:
    def test_builds_command_with_quoted_tokens(self):
        cmd = build_pip_install_command(["requests", "numpy>=1.26"])
        assert cmd == "pip install requests 'numpy>=1.26'"

    def test_empty_packages_builds_bare_command(self):
        # No tokens -> just "pip install" (callers decide whether to run it).
        assert build_pip_install_command([]) == "pip install"

    def test_propagates_validation_error(self):
        with pytest.raises(ValueError):
            build_pip_install_command(["--index-url=http://evil"])

    def test_propagates_over_limit_error(self):
        with pytest.raises(ValueError):
            build_pip_install_command([f"pkg{i}" for i in range(MAX_PACKAGES + 1)])
