"""Argon2id password hashing.

Uses argon2-cffi (BSD-3) directly. Defaults are OWASP-recommended; revisit
only if login latency is a measurable problem (likely won't be — argon2id
on modern hardware is ~30-80ms, well under any reasonable login budget).

Argon2 hashes self-describe their parameters, so changing the cost in a
future release doesn't break verification of older hashes — it just means
needs_rehash() returns True after a successful verify, and the login flow
should re-hash and persist.
"""
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHash,
    VerificationError,
    VerifyMismatchError,
)


_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Returns a self-describing argon2id hash string
    (typically ~95-100 chars). Raises ValueError on empty input.
    """
    if not plain:
        raise ValueError("password must not be empty")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext against a stored hash. Returns False on any mismatch
    or malformed hash. Constant-time within argon2-cffi.
    """
    try:
        _hasher.verify(hashed, plain)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False


def needs_rehash(hashed: str) -> bool:
    """True if the hash was produced with weaker parameters than current
    defaults. Call after a successful verify; if True, re-hash with
    hash_password() and persist the new value.
    """
    return _hasher.check_needs_rehash(hashed)
