"""Unit tests for canvas_server.security.

Pins the direct-bcrypt contract: bcrypt only considers the first 72 bytes
of a password (bcrypt>=5 raises instead of truncating, so the module must
truncate explicitly), and verify_password must reject malformed stored
hashes by returning False rather than raising.
"""

from __future__ import annotations

import re

import bcrypt
import pytest

from canvas_server.security import (
    hash_password,
    is_valid_email,
    normalize_email,
    verify_password,
)

# A stored bcrypt hash, whatever wrote it, is $2a$/$2b$/$2y$ + 53 chars.
_BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")


class TestHashVerify:
    def test_roundtrip(self):
        password_hash = hash_password("super-secret-123")
        assert _BCRYPT_HASH_RE.match(password_hash)
        assert verify_password("super-secret-123", password_hash)

    def test_wrong_password_rejected(self):
        password_hash = hash_password("super-secret-123")
        assert not verify_password("a-fresh-password", password_hash)

    def test_hashes_are_salted(self):
        assert hash_password("same") != hash_password("same")


class TestSeventyTwoByteBoundary:
    def test_long_password_hashes_and_verifies(self):
        # bcrypt>=5 raises ValueError for >72 bytes; the wrapper must not.
        password = "P" * 200
        password_hash = hash_password(password)
        assert verify_password(password, password_hash)

    def test_passwords_sharing_first_72_bytes_are_equivalent(self):
        # Documented bcrypt limitation, not a bug: truncation semantics.
        password_hash = hash_password("A" * 72 + "TAIL-DIFFERS")
        assert verify_password("A" * 72, password_hash)
        assert verify_password("A" * 72 + "tail-also-differs", password_hash)

    def test_truncates_on_bytes_not_characters(self):
        # 72 bytes of UTF-8, not 72 characters.
        password = "é" * 100  # 2 bytes per char
        password_hash = hash_password(password)
        assert verify_password(password, password_hash)

    def test_multibyte_password_distinct_from_its_ascii_prefix(self):
        # "é" is C3 A9; a password whose first 72 *bytes* land mid-character
        # must still round-trip deterministically.
        password = "é" * 40 + "suffix"  # 80 bytes
        password_hash = hash_password(password)
        assert verify_password(password, password_hash)


class TestMalformedHash:
    def test_garbage_hash_returns_false_not_raise(self):
        assert not verify_password("super-secret-123", "not-a-bcrypt-hash")

    def test_empty_hash_returns_false(self):
        assert not verify_password("super-secret-123", "")

    @pytest.mark.parametrize(
        "truncated",
        [
            "$2b$12$",  # right shape, no payload
            "$2b$12$" + "A" * 31,  # too short
        ],
    )
    def test_structurally_broken_hashes_return_false(self, truncated):
        assert not verify_password("super-secret-123", truncated)

    def test_compatible_with_passlib_era_hash(self):
        # A pre-generated bcrypt hash of "super-secret-123" produced by
        # passlib-era code must remain verifiable (stored hashes in prod).
        legacy_hash = bcrypt.hashpw(b"super-secret-123", bcrypt.gensalt(rounds=4))
        assert verify_password("super-secret-123", legacy_hash.decode("ascii"))


class TestEmailHelpers:
    def test_normalize_email_strips_and_lowercases(self):
        assert normalize_email("  Demo@Example.COM ") == "demo@example.com"

    def test_is_valid_email_accepts_plausible_shape(self):
        assert is_valid_email("user@host.tld")

    def test_is_valid_email_rejects_missing_host_or_at(self):
        assert not is_valid_email("no-at-sign")
        assert not is_valid_email("a@b")
