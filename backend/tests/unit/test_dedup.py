"""Table de cas — dédoublonnage approximatif (plan.md § 4 décision A, § 8 test le plus important).

Chaque ligne = deux fiches + le verdict attendu. Couvre chaque exclusion dure et chaque bande
de seuil. `expected` ∈ {"probable", "similar", "silent"} — cohérent avec `DedupVerdict.is_*`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.dedup import THRESHOLD_PROBABLE, THRESHOLD_SIMILAR, VehicleDraft, score_candidate

TODAY = date(2026, 8, 20)


def kangoo(**overrides: object) -> VehicleDraft:
    base: dict[str, object] = {
        "marque": "Renault",
        "modele": "Kangoo",
        "version": "Express",
        "vin_normalise": None,
        "immat_normalisee": None,
        "date_mise_en_circulation": date(2018, 5, 1),
        "kilometrage": 80000,
        "energie": "diesel",
        "date_proposition": TODAY,
        "state": None,
        "refus_commentaire": None,
    }
    base.update(overrides)
    return VehicleDraft(**base)  # type: ignore[arg-type]


# (id, vehicle_a, vehicle_b, expected, exclusion_reason_attendu)
CASES: list[tuple[str, VehicleDraft, VehicleDraft, str, str | None]] = [
    (
        "vin_identique_reste_proche -> probable (le VIN exact est bloqué en amont, ici on "
        "vérifie juste que l'identité ne casse pas le scoring)",
        kangoo(vin_normalise="VF1RJA0J123456789"),
        kangoo(vin_normalise="VF1RJA0J123456789", kilometrage=80100),
        "probable",
        None,
    ),
    (
        "vin_different -> exclusion dure, deux objets physiques distincts",
        kangoo(vin_normalise="VF1RJA0J123456789"),
        kangoo(vin_normalise="VF1RJA0J987654321"),
        "silent",
        "vin_different",
    ),
    (
        "5_kangoo_meme_societe_meme_jour_immats_differentes -> 0 alerte (cas nominal du métier, "
        "brief § 8) : l'opératrice saisit l'immatriculation, les fiches deviennent inéligibles",
        kangoo(immat_normalisee="AA123BB"),
        kangoo(immat_normalisee="CC456DD", kilometrage=80200),
        "silent",
        "immatriculation_different",
    ),
    (
        "immatriculation_identique -> pas d'exclusion, scoring haut",
        kangoo(immat_normalisee="AA123BB"),
        kangoo(immat_normalisee="AA123BB", kilometrage=80100),
        "probable",
        None,
    ),
    (
        "date_mise_en_circulation_ecart_superieur_12_mois -> exclusion dure",
        kangoo(date_mise_en_circulation=date(2018, 1, 1)),
        kangoo(date_mise_en_circulation=date(2019, 1, 2)),
        "silent",
        "date_mise_en_circulation_ecart_trop_grand",
    ),
    (
        "date_mise_en_circulation_ecart_exactement_365_jours -> pas d'exclusion (limite incluse)",
        kangoo(date_mise_en_circulation=date(2018, 1, 1)),
        kangoo(date_mise_en_circulation=date(2019, 1, 1), kilometrage=80100),
        "probable",
        None,
    ),
    (
        "kilometrage_ecart_superieur_5000 -> exclusion dure",
        kangoo(kilometrage=80000),
        kangoo(kilometrage=85001),
        "silent",
        "kilometrage_ecart_trop_grand",
    ),
    (
        "kilometrage_ecart_exactement_5000 -> pas d'exclusion (limite incluse)",
        kangoo(kilometrage=80000),
        kangoo(kilometrage=85000),
        "similar",
        None,
    ),
    (
        "marque_differente -> exclusion dure (similarité de marque < 0,90)",
        kangoo(marque="Peugeot", modele="Partner"),
        kangoo(marque="Renault", modele="Kangoo"),
        "silent",
        "marque_differente",
    ),
    (
        "vehicule_refuse_il_y_a_6_semaines -> alerte (critère d'acceptation explicite du brief)",
        kangoo(kilometrage=80500),
        kangoo(
            date_mise_en_circulation=date(2018, 5, 3),
            kilometrage=80000,
            date_proposition=TODAY - timedelta(days=42),
            state="REFUSE",
            refus_commentaire="Corrosion du châssis",
        ),
        "probable",
        None,
    ),
    (
        "meme_modele_annule -> le bonus terminal s'applique aussi à ANNULE",
        kangoo(kilometrage=80500),
        kangoo(
            date_mise_en_circulation=date(2018, 5, 3),
            kilometrage=80000,
            date_proposition=TODAY - timedelta(days=42),
            state="ANNULE",
        ),
        "probable",
        None,
    ),
    (
        "bande_similaire -> non bloquant, encart sous le formulaire",
        kangoo(kilometrage=82000),
        kangoo(kilometrage=79000, energie=None, date_proposition=TODAY - timedelta(days=20)),
        "similar",
        None,
    ),
    (
        "bonus_insuffisant_pour_changer_de_bande -> le bonus terminal ne repêche pas un score bas",
        kangoo(energie="essence"),
        VehicleDraft(
            marque="Renault",
            modele="Clio",
            version="Zen",
            vin_normalise=None,
            immat_normalisee=None,
            date_mise_en_circulation=date(2018, 9, 1),
            kilometrage=84500,
            energie="diesel",
            date_proposition=TODAY - timedelta(days=85),
            state="REFUSE",
        ),
        "silent",
        None,
    ),
    (
        "modeles_et_dates_eloignes -> silence, sans exclusion dure",
        kangoo(energie="essence"),
        VehicleDraft(
            marque="Renault",
            modele="Clio",
            version="Zen",
            vin_normalise=None,
            immat_normalisee=None,
            date_mise_en_circulation=date(2018, 9, 1),
            kilometrage=84500,
            energie="diesel",
            date_proposition=TODAY - timedelta(days=85),
            state=None,
        ),
        "silent",
        None,
    ),
    (
        "les_deux_energies_manquantes -> composante énergie neutre, pas d'exception",
        kangoo(energie=None),
        kangoo(energie=None, kilometrage=80100, date_proposition=TODAY - timedelta(days=5)),
        "probable",
        None,
    ),
    (
        "les_deux_kilometrages_manquants -> composante km neutre, pas d'exception",
        kangoo(kilometrage=None),
        kangoo(kilometrage=None, date_proposition=TODAY - timedelta(days=5)),
        "probable",
        None,
    ),
    (
        "aucune_donnee_distinctive_saisie_meme_jour -> score maximal, capé à 1.0",
        kangoo(),
        kangoo(state="REFUSE"),
        "probable",
        None,
    ),
]


@pytest.mark.parametrize("case_id,a,b,expected,exclusion_reason", CASES, ids=[c[0] for c in CASES])
def test_dedup_case_table(
    case_id: str,
    a: VehicleDraft,
    b: VehicleDraft,
    expected: str,
    exclusion_reason: str | None,
) -> None:
    verdict = score_candidate(a, b)

    if exclusion_reason is not None:
        assert verdict.excluded, case_id
        assert verdict.exclusion_reason == exclusion_reason, case_id

    actual = "probable" if verdict.is_probable else "similar" if verdict.is_similar else "silent"
    assert actual == expected, (
        f"{case_id}: score={verdict.score:.4f} excluded={verdict.excluded} "
        f"reason={verdict.exclusion_reason} components={verdict.components.as_dict()}"
    )


def test_thresholds_are_the_documented_values() -> None:
    """Garde-fou anti-régression sur les constantes nommées de la décision A."""
    assert THRESHOLD_PROBABLE == 0.85
    assert THRESHOLD_SIMILAR == 0.70


def test_score_never_exceeds_one() -> None:
    a = kangoo()
    b = kangoo(state="REFUSE")
    verdict = score_candidate(a, b)
    assert verdict.score <= 1.0
