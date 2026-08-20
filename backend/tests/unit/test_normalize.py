"""Normalisation VIN / immatriculation / modèle — décision A étape 0."""

from __future__ import annotations

from app.services.normalize import normalize_immatriculation, normalize_modele, normalize_vin


def test_normalize_vin_valid_17_chars() -> None:
    assert normalize_vin("VF1RJA0J123456789") == "VF1RJA0J123456789"
    assert normalize_vin("vf1 rja0j 123456789") == "VF1RJA0J123456789"
    assert normalize_vin("vf1-rja0j-123456789") == "VF1RJA0J123456789"


def test_normalize_vin_rejects_forbidden_letters() -> None:
    assert normalize_vin("VF1RJAOJ123456789") is None  # contient un 'O'
    assert normalize_vin("VF1RJAIJ123456789") is None  # contient un 'I'
    assert normalize_vin("VF1RJAQJ123456789") is None  # contient un 'Q'


def test_normalize_vin_rejects_wrong_length() -> None:
    assert normalize_vin("VF1RJA0J12345678") is None  # 16 caractères
    assert normalize_vin("VF1RJA0J1234567890") is None  # 18 caractères


def test_normalize_vin_empty_or_none() -> None:
    assert normalize_vin(None) is None
    assert normalize_vin("") is None
    assert normalize_vin("   ") is None


def test_normalize_immatriculation_siv() -> None:
    assert normalize_immatriculation("AA-123-BB") == "AA123BB"
    assert normalize_immatriculation("aa 123 bb") == "AA123BB"
    assert normalize_immatriculation("AA123BB") == "AA123BB"


def test_normalize_immatriculation_fni() -> None:
    assert normalize_immatriculation("123 ABC 75") == "123ABC75"


def test_normalize_immatriculation_empty() -> None:
    assert normalize_immatriculation(None) is None
    assert normalize_immatriculation("") is None


def test_normalize_immatriculation_strips_stray_punctuation() -> None:
    """Régression revue § 🟡 : une liste noire de séparateurs connus laissait passer toute
    autre ponctuation (`.`, `_`, `/`, ...), qui échappait alors à l'index unique partiel — deux
    saisies visuellement identiques ne se bloquaient pas mutuellement."""
    assert normalize_immatriculation("AA-123-BB.") == "AA123BB"
    assert normalize_immatriculation("AA.123.BB") == "AA123BB"
    assert normalize_immatriculation("AA_123_BB") == "AA123BB"
    assert normalize_immatriculation("AA/123/BB") == "AA123BB"


def test_normalize_immatriculation_same_value_different_punctuation_collide() -> None:
    """Le but recherché : deux saisies équivalentes doivent produire la MÊME valeur normalisée,
    donc être détectées comme le même véhicule par l'index unique partiel."""
    assert normalize_immatriculation("AA-123-BB.") == normalize_immatriculation("aa 123 bb")


def test_normalize_modele_strips_accents_and_case() -> None:
    assert normalize_modele("Renault", "Kangoo", "Express") == "renault kangoo express"
    assert normalize_modele("Citroën", "Berlingo", None) == "citroen berlingo"


def test_normalize_modele_compacts_punctuation_and_spaces() -> None:
    assert normalize_modele("Peugeot", "e-208", "GT-Line") == "peugeot e 208 gt line"
    assert normalize_modele("Renault", "  Kangoo   ZE  ", None) == "renault kangoo ze"


def test_normalize_modele_is_stable_regardless_of_input_case() -> None:
    a = normalize_modele("RENAULT", "KANGOO", "EXPRESS")
    b = normalize_modele("renault", "kangoo", "express")
    assert a == b
