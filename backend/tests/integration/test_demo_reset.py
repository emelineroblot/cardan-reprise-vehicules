"""`POST /admin/demo-reset` — plan.md § 8, cas 4.

Deux resets consécutifs produisent des compteurs identiques ; sans `CRON_SECRET` → 401.

⚠️ `run_demo_reset()` commite réellement (TRUNCATE + seed) sur la base de test, hors du
mécanisme de transaction-par-test (§ 4 décision F) — nécessaire puisque le reset gère lui-même
ses transactions (autocommit pour `REFRESH CONCURRENTLY`). On restaure une base vide en fin de
test pour ne pas polluer les tests suivants.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.config import get_settings
from app.models.user import AppUser
from app.seed.reset import OPERATIONAL_TABLES, run_demo_reset

settings = get_settings()


def _truncate_all(engine) -> None:
    table_list = ", ".join(f"public.{name}" for name in OPERATIONAL_TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE"))


def test_two_consecutive_resets_produce_identical_counters(engine) -> None:
    try:
        first = run_demo_reset()
        second = run_demo_reset()

        assert first["status"] == "succes"
        assert second["status"] == "succes"
        assert first["rows_created"] == second["rows_created"]
        assert second["rows_created"] == {
            "accounts": 4,
            "checklist_items": 14,
            "companies": 12,
            "vehicles": 90,
        }
    finally:
        _truncate_all(engine)


def test_reset_is_atomic_truncate_not_kept_on_seed_failure(engine, monkeypatch) -> None:
    """Régression revue § 🟠 : si le seed échoue après le TRUNCATE, la base ne doit pas rester
    vide — le TRUNCATE doit être annulé avec le reste (même transaction, même session)."""
    from app.db.session import SessionLocal

    try:
        # État de départ connu et non vide.
        first = run_demo_reset()
        assert first["status"] == "succes"
        with SessionLocal() as check_db:
            before_count = len(list(check_db.execute(select(AppUser)).scalars().all()))
        assert before_count == 4

        def _boom(db, *, force=False):
            raise RuntimeError("échec simulé du seed démo")

        monkeypatch.setattr("app.seed.reset.seed_demo", _boom)

        try:
            run_demo_reset()
            raise AssertionError("run_demo_reset() aurait dû lever RuntimeError")
        except RuntimeError:
            pass

        with SessionLocal() as check_db:
            after_count = len(list(check_db.execute(select(AppUser)).scalars().all()))
        assert after_count == before_count, (
            "le TRUNCATE a été conservé malgré l'échec du seed : le reset n'est pas atomique "
            f"(attendu {before_count} comptes, obtenu {after_count})"
        )
    finally:
        _truncate_all(engine)


def test_demo_reset_endpoint_without_secret_returns_401(client: TestClient) -> None:
    response = client.post("/api/v1/admin/demo-reset")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_demo_reset_endpoint_with_wrong_secret_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/admin/demo-reset", headers={"Authorization": "Bearer wrong-secret"}
    )
    assert response.status_code == 401


def test_demo_reset_endpoint_with_correct_secret_succeeds(client: TestClient, engine) -> None:
    try:
        response = client.post(
            "/api/v1/admin/demo-reset",
            headers={"Authorization": f"Bearer {settings.cron_secret}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "succes"
    finally:
        _truncate_all(engine)


def test_demo_reset_endpoint_accepts_get_for_vercel_cron(client: TestClient, engine) -> None:
    """Régression revue § 🟠 : Vercel invoque les cron jobs par GET, jamais POST — sans cette
    route, le cron nocturne échouerait en 405 chaque nuit, silencieusement."""
    try:
        response = client.get(
            "/api/v1/admin/demo-reset",
            headers={"Authorization": f"Bearer {settings.cron_secret}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "succes"
    finally:
        _truncate_all(engine)


def test_demo_reset_get_without_secret_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/admin/demo-reset")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_demo_reset_non_ascii_authorization_header_returns_401_not_500(
    client: TestClient,
) -> None:
    """Régression revue § 🟡 : `hmac.compare_digest` lève `TypeError` sur une chaîne non-ASCII
    en comparaison `str` — doit rester un 401 propre, jamais un 500.

    L'en-tête est envoyé en `bytes` (latin-1, comme la RFC 7230 l'autorise pour une valeur
    d'en-tête HTTP) : `httpx` refuse d'encoder une valeur `str` non-ASCII en sortie, ce qui
    masquerait le comportement serveur réellement testé ici.
    """
    response = client.post(
        "/api/v1/admin/demo-reset",
        headers={"Authorization": "Bearer clé-erronée-é".encode("latin-1")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
