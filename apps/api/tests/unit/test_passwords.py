"""Unit tests: Argon2id password hashing and rehash detection (task 2.1).

The production module ``raguard_api.auth.passwords`` does not exist yet — these
tests drive its API: vetted-hash verification (never homegrown crypto), wrong
passwords and malformed hashes fail without raising or leaking, and rehash
detection catches parameter drift.
"""

import pytest
from argon2 import PasswordHasher
from raguard_api.auth.passwords import hash_password, needs_rehash, verify_password

pytestmark = pytest.mark.unit

PASSWORD = "correct horse battery staple"


def test_verify_correct_password_succeeds():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_verify_wrong_password_fails():
    assert verify_password("wrong password", hash_password(PASSWORD)) is False


def test_verify_malformed_hash_returns_false_without_raising():
    assert verify_password("anything", "not-a-valid-hash") is False


def test_hashes_are_salted_argon2id_and_unique():
    hashes = {hash_password("same password") for _ in range(2)}
    assert len(hashes) == 2
    assert all(value.startswith("$argon2id$") for value in hashes)


def test_needs_rehash_detects_parameter_drift_and_defaults():
    legacy = PasswordHasher(time_cost=2).hash(PASSWORD)
    assert needs_rehash(legacy) is True
    assert needs_rehash(hash_password(PASSWORD)) is False
