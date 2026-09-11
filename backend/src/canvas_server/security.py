"""Password hashing (bcrypt, used directly — passlib is unmaintained and
incompatible with bcrypt>=5) and email normalization helpers."""

from __future__ import annotations

import re

import bcrypt

# bcrypt only considers the first 72 bytes of a password, and bcrypt>=5
# raises instead of silently truncating. Truncate explicitly to keep the
# classic semantics (and hashes written by passlib-era code verifiable).
_MAX_BCRYPT_BYTES = 72

# Minimal email shape validation (avoids the email-validator dependency).
# We intentionally do not enforce deliverability — the email is a login handle.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """Normalize an email to its canonical login handle: stripped + lowercased."""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """True if *email* has a plausible user@host.tld shape."""
    return bool(_EMAIL_RE.match(email.strip()))


def _to_bcrypt_bytes(password: str) -> bytes:
    """Encode *password* and keep only the first 72 bytes bcrypt would use."""
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify of *password* against a stored bcrypt hash.

    Returns False (rather than raising) for malformed stored hashes.
    """
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False
