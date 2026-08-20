"""`hash_password`/`verify_password` — argon2id, plan.md § 3.4."""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", hashed) is True


def test_verify_password_rejects_incorrect_password() -> None:
    hashed = hash_password("s3cret-pass")
    assert verify_password("wrong-pass", hashed) is False


def test_verify_password_rejects_corrupted_hash_without_raising() -> None:
    """Régression revue § 🟡 : un `password_hash` corrompu (`InvalidHashError`) doit rester un
    refus d'authentification, jamais une exception qui remonterait en 500."""
    assert verify_password("whatever", "not-a-valid-argon2-hash") is False


def test_verify_password_rejects_empty_hash_without_raising() -> None:
    assert verify_password("whatever", "") is False
