"""Password hashing (bcrypt via passlib) and email normalization helpers."""

from __future__ import annotations

import re

from passlib.context import CryptContext

# bcrypt is the configured hashing scheme (per #32).
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Minimal email shape validation (avoids the email-validator dependency).
# We intentionally do not enforce deliverability — the email is a login handle.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    """Normalize an email to its canonical login handle: stripped + lowercased."""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """True if *email* has a plausible user@host.tld shape."""
    return bool(_EMAIL_RE.match(email.strip()))


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify of *password* against a stored bcrypt hash."""
    return _pwd_context.verify(password, password_hash)
