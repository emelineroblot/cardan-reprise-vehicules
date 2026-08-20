"""Validation locale du SIRET — décision B : « 14 chiffres et clé de Luhn valide (avec
l'exception connue `356000000` pour La Poste) → 422 sans aucun appel réseau ».
"""

from __future__ import annotations

import re

_SIRET_RE = re.compile(r"^[0-9]{14}$")

# La Poste (SIREN 356000000) est l'exception documentée : ses SIRET ne respectent pas
# l'algorithme de Luhn standard pour des raisons historiques (changement de numérotation).
LA_POSTE_SIREN = "356000000"


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def is_valid_siret(siret: str) -> bool:
    """14 chiffres + clé de Luhn valide, avec l'exception La Poste."""
    if not _SIRET_RE.match(siret):
        return False
    if siret[:9] == LA_POSTE_SIREN:
        # Le SIREN de La Poste est un cas connu : ses établissements ne valident pas Luhn.
        return True
    return _luhn_valid(siret)


def normalize_siret(raw: str) -> str:
    """Retire espaces et tirets, ne garde que les chiffres."""
    return re.sub(r"[^0-9]", "", raw)
