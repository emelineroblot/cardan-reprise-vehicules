"""Table de cas — validation locale du SIRET (Luhn + exception La Poste, décision B)."""

from __future__ import annotations

import pytest

from app.services.siret import is_valid_siret, normalize_siret

# SIRET valides connus (Luhn OK) — utilisés aussi par le jeu de démo (préchargés en cache).
VALID_SIRETS = [
    "73282932000074",  # SIREN 732829320 (générique, Luhn valide)
    "55210055443880",
]

CASES: list[tuple[str, bool, str]] = [
    ("73282932000074", True, "SIRET générique Luhn valide"),
    ("55210055443880", True, "SIRET générique Luhn valide (2)"),
    ("35600000000048", True, "SIREN La Poste — exception documentée"),
    ("12345678901234", False, "14 chiffres, Luhn invalide"),
    ("7328293200007", False, "13 chiffres — trop court"),
    ("732829320000745", False, "15 chiffres — trop long"),
    ("7328293200007A", False, "caractère non numérique"),
    ("", False, "chaîne vide"),
    ("00000000000000", True, "que des zéros — Luhn techniquement valide (somme nulle)"),
]


@pytest.mark.parametrize("siret,expected,description", CASES, ids=[c[2] for c in CASES])
def test_is_valid_siret(siret: str, expected: bool, description: str) -> None:
    assert is_valid_siret(siret) is expected, description


def test_normalize_siret_strips_spaces_and_dashes() -> None:
    assert normalize_siret("732 829 320 00074") == "73282932000074"
    assert normalize_siret("732-829-320-00074") == "73282932000074"


def test_valid_sirets_used_in_demo_seed_are_actually_valid() -> None:
    """Garde-fou : le jeu de démo précharge des SIRET fictifs à clé de Luhn valide
    (plan.md § 4 décision B) — s'ils cessent de l'être, le seed casserait silencieusement."""
    for siret in VALID_SIRETS:
        assert is_valid_siret(siret)
