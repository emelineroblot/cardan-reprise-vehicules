"""Normalisation VIN / immatriculation / modèle — plan.md § 4 décision A, étape 0.

Ces fonctions sont pures (aucune dépendance base) : testables unitairement.
"""

from __future__ import annotations

import re
import unicodedata

# I, O, Q interdits dans un VIN (17 caractères) — norme ISO 3779.
_VIN_FORBIDDEN = {"I", "O", "Q"}
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# Immatriculation française SIV : AA-123-AA → normalisée en AA123AA. Liste blanche des
# caractères alphanumériques (comme `normalize_vin`), pas une liste noire de séparateurs connus
# — sans quoi un caractère de ponctuation quelconque (« AA-123-BB. ») survit à la normalisation
# et échappe à l'index unique partiel, donc au blocage de doublon exact (revue § 🟡).
_IMMAT_KEEP_RE = re.compile(r"[^A-Za-z0-9]")


def normalize_vin(raw: str | None) -> str | None:
    """Majuscules, sans espaces ni tirets. `None` si vide ou si le format ne peut pas être un VIN
    (17 caractères, sans I/O/Q) — un VIN mal saisi n'est simplement pas indexé pour le doublon."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s\-]", "", raw).upper()
    if not cleaned:
        return None
    if len(cleaned) != 17:
        return None
    if any(ch in _VIN_FORBIDDEN for ch in cleaned):
        return None
    if not _VIN_RE.match(cleaned):
        return None
    return cleaned


def normalize_immatriculation(raw: str | None) -> str | None:
    """Ramène à la forme compacte `AA123BB` (SIV) ou `123ABC75` (FNI) — ne garde que les
    caractères alphanumériques, en majuscules."""
    if not raw:
        return None
    cleaned = _IMMAT_KEEP_RE.sub("", raw).upper()
    return cleaned or None


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_modele(marque: str, modele: str, version: str | None = None) -> str:
    """`norm()` de la décision A : minuscules, accents retirés, ponctuation/tirets supprimés,
    espaces compactés. Sert au scoring `token_set_ratio` du dédoublonnage."""
    raw = " ".join(part for part in (marque, modele, version) if part)
    no_accents = _strip_accents(raw).lower()
    no_punct = re.sub(r"[^\w\s]", " ", no_accents)
    compact = re.sub(r"\s+", " ", no_punct).strip()
    return compact
