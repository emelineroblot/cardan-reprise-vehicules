"""`DisabledProvider` — tests et mode démo hors ligne : répond immédiatement `unavailable`."""

from __future__ import annotations

from app.services.company_lookup.base import CompanyLookupResult, CompanyLookupUnavailable


class DisabledProvider:
    name = "disabled"

    def lookup(self, siret: str) -> CompanyLookupResult:
        raise CompanyLookupUnavailable("Provider désactivé (COMPANY_LOOKUP_PROVIDER=disabled).")
