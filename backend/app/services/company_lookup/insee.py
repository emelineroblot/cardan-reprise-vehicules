"""`SireneInseeProvider` — activé si `INSEE_API_KEY` est présente (décision B).

Même interface, même schéma de sortie normalisé que `RechercheEntreprisesProvider`.
`GET https://api.insee.fr/entreprises/sirene/V3.11/siret/{siret}` (clé Bearer).
"""

from __future__ import annotations

import time

import httpx

from app.services.company_lookup.base import (
    CompanyLookupNotFound,
    CompanyLookupResult,
    CompanyLookupUnavailable,
)

BASE_URL = "https://api.insee.fr/entreprises/sirene/V3.11/siret"
TIMEOUT = httpx.Timeout(connect=2.5, read=2.5, write=2.5, pool=2.5)


class SireneInseeProvider:
    name = "insee"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def lookup(self, siret: str) -> CompanyLookupResult:
        headers = {"X-INSEE-Api-Key-Integration": self._api_key}
        try:
            response = self._get_with_retry(siret, headers)
        except httpx.TimeoutException as exc:
            raise CompanyLookupUnavailable("Délai dépassé.") from exc
        except httpx.HTTPError as exc:
            raise CompanyLookupUnavailable(str(exc)) from exc

        if response.status_code == 404:
            raise CompanyLookupNotFound(siret)
        if response.status_code != 200:
            raise CompanyLookupUnavailable(f"HTTP {response.status_code}")

        etablissement = response.json().get("etablissement", {})
        unite_legale = etablissement.get("uniteLegale", {})
        adresse = etablissement.get("adresseEtablissement", {})

        prenom = unite_legale.get("prenom1UniteLegale", "")
        nom = unite_legale.get("nomUniteLegale", "")
        denomination = unite_legale.get("denominationUniteLegale") or f"{prenom} {nom}".strip()
        adresse_ligne1 = " ".join(
            part
            for part in (
                adresse.get("numeroVoieEtablissement"),
                adresse.get("typeVoieEtablissement"),
                adresse.get("libelleVoieEtablissement"),
            )
            if part
        )

        return CompanyLookupResult(
            siret=etablissement.get("siret", siret),
            siren=unite_legale.get("siren", siret[:9]),
            denomination=denomination or "",
            forme_juridique=unite_legale.get("categorieJuridiqueUniteLegale"),
            code_naf=etablissement.get("activitePrincipaleEtablissement"),
            libelle_naf=None,
            adresse_ligne1=adresse_ligne1,
            code_postal=adresse.get("codePostalEtablissement", ""),
            commune=adresse.get("libelleCommuneEtablissement", ""),
            tranche_effectif=unite_legale.get("trancheEffectifsUniteLegale"),
            date_creation=unite_legale.get("dateCreationUniteLegale"),
        )

    def _get_with_retry(self, siret: str, headers: dict[str, str]) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    response = client.get(f"{BASE_URL}/{siret}", headers=headers)
                if response.status_code == 404 or response.status_code < 500:
                    return response
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                return response
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise CompanyLookupUnavailable("Échec inattendu.")
