"""Tests for app.auth.password (argon2id wrapper).

No DB; pure unit tests.
"""
import pytest

from app.auth.password import hash_password, verify_password, needs_rehash


def test_hash_password_produces_argon2id_format():
    h = hash_password("hunter2")
    assert h.startswith("$argon2id$")


def test_hash_password_rejects_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        hash_password("")


def test_verify_password_accepts_correct():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_rejects_wrong():
    h = hash_password("hunter2")
    assert verify_password("hunter3", h) is False


def test_verify_password_rejects_malformed_hash():
    assert verify_password("hunter2", "not-a-real-hash") is False


def test_verify_password_rejects_empty_hash():
    assert verify_password("hunter2", "") is False


def test_each_hash_is_unique_due_to_random_salt():
    """Salt randomness guarantees identical passwords don't share hashes —
    important defense against rainbow tables and hash-equality probing.
    """
    h1 = hash_password("hunter2")
    h2 = hash_password("hunter2")
    assert h1 != h2
    assert verify_password("hunter2", h1) is True
    assert verify_password("hunter2", h2) is True


def test_needs_rehash_false_for_fresh_hash():
    """A hash produced with current parameters never needs rehashing
    immediately. needs_rehash only returns True if cost params have moved
    upward in a later release."""
    h = hash_password("hunter2")
    assert needs_rehash(h) is False


def test_verify_unicode_password():
    """Argon2 handles non-ASCII passwords correctly."""
    h = hash_password("পাসওয়ার্ড123")
    assert verify_password("পাসওয়ার্ড123", h) is True
    assert verify_password("পাসওয়ার্ড124", h) is False


def test_verify_long_password():
    """Argon2 doesn't have bcrypt's 72-byte truncation issue."""
    long_pw = "x" * 200
    h = hash_password(long_pw)
    assert verify_password(long_pw, h) is True
    assert verify_password("x" * 199, h) is False
