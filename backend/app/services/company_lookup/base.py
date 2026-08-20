"""Port `CompanyLookupProvider` — décision B (plan.md § 4). Trois implémentations, même contrat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompanyLookupResult:
    """Schéma de sortie normalisé, identique quel que soit le provider."""

    siret: str
    siren: str
    denomination: str
    forme_juridique: str | None
    code_naf: str | None
    libelle_naf: str | None
    adresse_ligne1: str
    code_postal: str
    commune: str
    tranche_effectif: str | None
    date_creation: str | None  # ISO date, converti par l'appelant


class CompanyLookupNotFound(Exception):
    """Le SIRET est syntaxiquement valide mais introuvable côté provider (404)."""


class CompanyLookupUnavailable(Exception):
    """Timeout, erreur réseau ou 5xx — le provider est temporairement indisponible."""


class CompanyLookupProvider(Protocol):
    name: str

    def lookup(self, siret: str) -> CompanyLookupResult:
        """Lève `CompanyLookupNotFound` ou `CompanyLookupUnavailable` en cas d'échec."""
        ...
