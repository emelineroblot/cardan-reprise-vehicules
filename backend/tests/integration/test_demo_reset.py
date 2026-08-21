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


def _null_safe_sort_key(row: tuple) -> tuple:
    """De nombreuses colonnes de mart sont volontairement `NULL` (jamais 0 — § règle non
    négociable de la marge/du délai/du taux de refus), ce qu'un tri par tuple Python ne sait pas
    comparer nativement (`TypeError` entre `None` et `int`). Chaque élément devient `(is_none,
    valeur_ou_None)` : les `None` se regroupent entre eux sans jamais être comparés à une vraie
    valeur."""
    return tuple((item is None, item) for item in row)


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
            # J3 — atelier (work_order/work_order_line) et coûts hors atelier (vehicle_cost),
            # comptes déterministes (même graine, mêmes règles de génération) : la valeur exacte
            # n'est pas ce qui compte (elle bougerait au moindre ajustement de proportion dans
            # `app/seed/demo.py`), c'est que `first == second` ci-dessus le prouve déjà — cette
            # assertion documente en plus la valeur actuelle en clair.
            "work_orders": 28,
            "work_order_lines": 32,
            # Correctif revue finale J3 § 🟠 n°5 : `_force_at_least_one_negative_margin` insère
            # bien une 35e ligne `vehicle_cost` (forçage de la marge négative), mais sa valeur de
            # retour était jetée par l'appelant — `created_vehicle_costs` restait bloqué à 34
            # alors que `SELECT count(*) FROM vehicle_cost` valait déjà 35. Comptage corrigé
            # (`app/seed/demo.py`), valeur ici alignée sur le compte réel.
            "vehicle_costs": 35,
            # Correctif post-J3 (tests-j3.md § 3, gap J2) : le seed peuple désormais le module
            # terrain (mission/inspection/photo/notification) — mêmes considérations que
            # ci-dessus, la valeur exacte importe moins que `first == second`, documentée ici en
            # clair. `photos` couvre les deux familles (angles de contrôle + avant/après travaux).
            "missions": 70,
            "inspections": 48,
            "photos": 583,
            "notifications": 70,
        }
    finally:
        _truncate_all(engine)


def test_two_consecutive_resets_produce_identical_dashboard_figures(engine) -> None:
    """La démo publique est réinitialisée chaque nuit (cron Vercel) — si les chiffres du
    tableau de bord bougeaient d'une nuit à l'autre, l'étude de cas deviendrait fausse. Ne
    vérifie pas seulement les compteurs de lignes (`test_two_consecutive_resets_produce_
    identical_counters` ci-dessus) mais le **contenu numérique** des marts eux-mêmes :
    `run_demo_reset()` appelle `analytics build`+`refresh` (autocommit, § 4 décision F) à
    chaque passage, donc les marts existent déjà et sont comparables directement en base sans
    passer par un endpoint HTTP.
    """
    try:
        first = run_demo_reset()
        assert first["status"] == "succes"
        with engine.connect() as conn:
            first_kpi = dict(
                conn.execute(text("SELECT * FROM analytics.mart_kpi_global")).mappings().one()
            )
            # `vehicle_id`/`reference` changent à chaque reset (UUID/séquence régénérés) : seules
            # les valeurs numériques comparent le contenu réel du dashboard, triées pour ne pas
            # dépendre d'un ordre de ligne accidentellement stable.
            first_marges = sorted(
                (
                    (row.marge_cents, row.marge_pct, row.has_marge)
                    for row in conn.execute(
                        text(
                            "SELECT marge_cents, marge_pct, has_marge "
                            "FROM analytics.mart_vehicule_marge"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            first_refus = sorted(
                (
                    tuple(row)
                    for row in conn.execute(
                        text(
                            "SELECT mois, type_flotte, nb_proposes, nb_refuses, taux_refus "
                            "FROM analytics.mart_refus"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            first_travaux = sorted(
                (
                    tuple(row)
                    for row in conn.execute(
                        text(
                            "SELECT mois, type, volume, nb_clos, cout_moyen_reel_cents, "
                            "ecart_estime_reel_cents FROM analytics.mart_travaux"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            first_cycle = sorted(
                (
                    (
                        row.delai_saisie_affectation_heures,
                        row.delai_affectation_controle_heures,
                        row.delai_controle_decision_heures,
                        row.delai_total_heures,
                    )
                    for row in conn.execute(
                        text(
                            "SELECT delai_saisie_affectation_heures, "
                            "delai_affectation_controle_heures, "
                            "delai_controle_decision_heures, delai_total_heures "
                            "FROM analytics.mart_cycle_temps"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )

        second = run_demo_reset()
        assert second["status"] == "succes"
        with engine.connect() as conn:
            second_kpi = dict(
                conn.execute(text("SELECT * FROM analytics.mart_kpi_global")).mappings().one()
            )
            second_marges = sorted(
                (
                    (row.marge_cents, row.marge_pct, row.has_marge)
                    for row in conn.execute(
                        text(
                            "SELECT marge_cents, marge_pct, has_marge "
                            "FROM analytics.mart_vehicule_marge"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            second_refus = sorted(
                (
                    tuple(row)
                    for row in conn.execute(
                        text(
                            "SELECT mois, type_flotte, nb_proposes, nb_refuses, taux_refus "
                            "FROM analytics.mart_refus"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            second_travaux = sorted(
                (
                    tuple(row)
                    for row in conn.execute(
                        text(
                            "SELECT mois, type, volume, nb_clos, cout_moyen_reel_cents, "
                            "ecart_estime_reel_cents FROM analytics.mart_travaux"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )
            second_cycle = sorted(
                (
                    (
                        row.delai_saisie_affectation_heures,
                        row.delai_affectation_controle_heures,
                        row.delai_controle_decision_heures,
                        row.delai_total_heures,
                    )
                    for row in conn.execute(
                        text(
                            "SELECT delai_saisie_affectation_heures, "
                            "delai_affectation_controle_heures, "
                            "delai_controle_decision_heures, delai_total_heures "
                            "FROM analytics.mart_cycle_temps"
                        )
                    )
                ),
                key=_null_safe_sort_key,
            )

        # `snapshot_key` mis à part (constante), le reste des tuiles KPI doit être identique.
        first_kpi.pop("snapshot_key", None)
        second_kpi.pop("snapshot_key", None)
        assert first_kpi == second_kpi, (
            "les tuiles du tableau de bord (mart_kpi_global) diffèrent entre deux demo-reset "
            "consécutifs — la démo publique, réinitialisée chaque nuit, afficherait des chiffres "
            "différents d'un jour à l'autre"
        )
        assert first_marges == second_marges
        assert first_refus == second_refus
        assert first_travaux == second_travaux
        assert first_cycle == second_cycle
        # Rappel non négociable, revérifié à chaque reset : au moins une marge négative, au
        # moins une marge NULL (has_marge=false) — sans quoi une régression du seed pourrait
        # rendre ce test vert par absence de cas, pas par exactitude.
        assert any(
            marge_cents is not None and marge_cents < 0 for marge_cents, _pct, _has in first_marges
        )
        assert any(has_marge is False for _cents, _pct, has_marge in first_marges)
    finally:
        _truncate_all(engine)


def test_mart_kpi_global_matches_known_reference_values(engine) -> None:
    """Fige les 9 chiffres du tableau de bord (hors `snapshot_key`) sur le jeu de démo connu —
    garde-fou distinct de `test_two_consecutive_resets_produce_identical_dashboard_figures`
    ci-dessus, qui ne compare le mart qu'à **lui-même** entre deux exécutions du même code :
    par construction, ce test-là ne peut pas détecter qu'un changement (une nouvelle formule de
    mart, un `rng.random()` ajouté dans la mauvaise boucle du seed) a déplacé un indicateur, tant
    que les deux exécutions restent cohérentes entre elles. Ce mode de défaillance a déjà frappé
    ce projet deux fois en silence (kilométrage du véhicule de dédoublonnage, délais de cycle
    négatifs) : ce test-ci sert de filet contre une troisième occurrence.

    Si cette assertion casse : ce n'est pas forcément un bug. Un changement volontaire du seed ou
    d'une formule de mart peut légitimement déplacer ces chiffres — mais l'auteur du changement
    doit alors mettre à jour les valeurs ci-dessous **en connaissance de cause** (et le
    documenter dans `implementation.md`), pas laisser un test rouge passer inaperçu ni le
    corriger sans comprendre pourquoi le chiffre a bougé.
    """
    try:
        result = run_demo_reset()
        assert result["status"] == "succes"
        with engine.connect() as conn:
            kpi = dict(
                conn.execute(
                    text(
                        "SELECT nb_vehicules_total, nb_vehicules_actifs, nb_achats_valides, "
                        "nb_refuses, taux_refus_global::float8 AS taux_refus_global, "
                        "marge_moyenne_cents::bigint AS marge_moyenne_cents, "
                        "nb_marges_negatives, "
                        "delai_cycle_moyen_heures::float8 AS delai_cycle_moyen_heures, "
                        "cout_travaux_moyen_cents::bigint AS cout_travaux_moyen_cents "
                        "FROM analytics.mart_kpi_global"
                    )
                )
                .mappings()
                .one()
            )

        # Valeurs mesurées et documentées par la revue de vérification finale J3
        # (review-j3-finale.md § 🟠 n°3) sur le jeu de démo déterministe (SEED_VERSION figé).
        reference_ints = {
            "nb_vehicules_total": 90,
            "nb_vehicules_actifs": 56,
            "nb_achats_valides": 16,
            "nb_refuses": 16,
            "marge_moyenne_cents": 258325,
            "nb_marges_negatives": 1,
            "cout_travaux_moyen_cents": 73635,
        }
        # Comparaison approchée : `float8` en base et `float` Python peuvent différer d'un
        # dernier bit selon le chemin de conversion, sans que ça n'indique une vraie divergence.
        reference_floats = {
            "taux_refus_global": 0.1818,
            "delai_cycle_moyen_heures": 183.2,
        }
        mismatches = {
            key: {"obtenu": kpi[key], "attendu": expected}
            for key, expected in reference_ints.items()
            if kpi[key] != expected
        }
        mismatches.update(
            {
                key: {"obtenu": kpi[key], "attendu": expected}
                for key, expected in reference_floats.items()
                if abs(kpi[key] - expected) > 1e-4
            }
        )
        assert mismatches == {}, (
            "un ou plusieurs indicateurs du tableau de bord (analytics.mart_kpi_global) ont "
            f"changé de valeur sur le jeu de démo connu : {mismatches}. Le jeu de démo sert "
            "d'étude de cas publique qui cite ces chiffres — si ce déplacement est volontaire "
            "(nouvelle formule de mart, seed modifié), mets à jour les dictionnaires de "
            "référence ci-dessus en connaissance de cause ; sinon c'est une régression "
            "silencieuse à investiguer avant de toucher au test."
        )
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

        def _boom(db, *, force=False, storage=None, **kwargs):
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


def test_seed_photo_purge_replaces_previous_generation_without_losing_current_photos(
    engine,
) -> None:
    """Correctif revue finale J3 § 🟠 n°6 : la purge du préfixe `seed/` a été déplacée après le
    commit du reset (`app/seed/demo.py::snapshot_stale_seed_photo_prefixes` /
    `purge_stale_seed_photos`), sélective sur les sous-répertoires photographiés *avant* le run
    courant — jamais un `delete_prefix("seed/")` global, qui emporterait aussi les photos que le
    run courant vient d'écrire (les identifiants de véhicule sont des `uuid4()` non seedés :
    aucune collision, donc aucun recouvrement entre deux générations). Vérifie ici la
    contrepartie du correctif : après un deuxième reset réussi, la génération précédente a bien
    disparu du disque et la génération courante y est entièrement lisible."""
    from app.services.storage.service import get_storage_backend

    storage = get_storage_backend()

    try:
        first = run_demo_reset()
        assert first["status"] == "succes"
        with engine.connect() as conn:
            first_keys = {
                (row.storage_bucket, row.storage_key)
                for row in conn.execute(text("SELECT storage_bucket, storage_key FROM photo"))
            }
        assert len(first_keys) > 0

        second = run_demo_reset()
        assert second["status"] == "succes"
        with engine.connect() as conn:
            second_keys = {
                (row.storage_bucket, row.storage_key)
                for row in conn.execute(text("SELECT storage_bucket, storage_key FROM photo"))
            }
        assert len(second_keys) > 0

        assert first_keys.isdisjoint(second_keys), (
            "les deux générations partagent des clés de stockage — inattendu avec des "
            "identifiants de véhicule en uuid4()"
        )

        unreadable = [
            f"{bucket}/{key}"
            for bucket, key in second_keys
            if not storage.exists(bucket=bucket, key=key)
        ]
        assert unreadable == [], f"photo(s) de la génération courante illisible(s) : {unreadable}"

        leftover = [
            f"{bucket}/{key}"
            for bucket, key in first_keys
            if storage.exists(bucket=bucket, key=key)
        ]
        assert leftover == [], (
            f"photo(s) de la génération précédente non purgée(s) du disque : {leftover}"
        )
    finally:
        _truncate_all(engine)


def test_reset_failure_after_disk_write_does_not_lose_previous_seed_photos(
    engine, monkeypatch
) -> None:
    """Régression revue finale J3 § 🟠 n°6 (le défaut d'origine) : si le seed échoue **après**
    avoir écrit ses nouveaux fichiers sur disque mais **avant** le commit, les photos de la
    génération précédente — celles que la base référence toujours après le rollback — doivent
    rester lisibles. C'est exactement le scénario qui cassait avant ce correctif : la purge du
    préfixe `seed/` s'exécutait en tout début de `seed_demo`, donc avant l'échec simulé
    ci-dessous ; un rollback laissait alors la base revenir à son état de la veille pendant que
    les fichiers avaient déjà disparu du disque (vignettes cassées, 404 silencieux, aucune
    erreur applicative — le piège documenté dans `docs/wiki/pieges-projet.md`)."""
    from app.services.storage.service import get_storage_backend

    storage = get_storage_backend()

    try:
        first = run_demo_reset()
        assert first["status"] == "succes"
        with engine.connect() as conn:
            keys_before_failure = {
                (row.storage_bucket, row.storage_key)
                for row in conn.execute(text("SELECT storage_bucket, storage_key FROM photo"))
            }
        assert len(keys_before_failure) > 0

        from app.seed.demo import seed_demo as real_seed_demo

        def _boom_after_disk_write(db, *, force=False, storage=None, **kwargs):
            real_seed_demo(db, force=force, storage=storage, **kwargs)
            raise RuntimeError("échec simulé après écriture disque, avant commit")

        monkeypatch.setattr("app.seed.reset.seed_demo", _boom_after_disk_write)

        try:
            run_demo_reset()
            raise AssertionError("run_demo_reset() aurait dû lever RuntimeError")
        except RuntimeError:
            pass

        with engine.connect() as conn:
            keys_after_failure = {
                (row.storage_bucket, row.storage_key)
                for row in conn.execute(text("SELECT storage_bucket, storage_key FROM photo"))
            }
        assert keys_after_failure == keys_before_failure, (
            "le rollback en base n'a pas laissé les mêmes lignes photo qu'avant l'échec"
        )

        missing = [
            f"{bucket}/{key}"
            for bucket, key in keys_after_failure
            if not storage.exists(bucket=bucket, key=key)
        ]
        assert missing == [], (
            "photo(s) référencée(s) en base mais disparue(s) du disque après un reset en échec "
            f"(vignette cassée silencieuse) : {missing}"
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
