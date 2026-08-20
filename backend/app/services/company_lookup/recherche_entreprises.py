"""`RechercheEntreprisesProvider` — défaut, sans authentification (décision B).

`GET https://recherche-entreprises.api.gouv.fr/search?q={siret}&page=1&per_page=1`,
lecture de `matching_etablissements` / `siege`.
"""

from __future__ import annotations

import httpx

from app.services.company_lookup.base import (
    CompanyLookupNotFound,
    CompanyLookupResult,
    CompanyLookupUnavailable,
)

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"
TIMEOUT = httpx.Timeout(connect=2.5, read=2.5, write=2.5, pool=2.5)


class RechercheEntreprisesProvider:
    name = "recherche_entreprises"

    def lookup(self, siret: str) -> CompanyLookupResult:
        try:
            response = self._get_with_retry(siret)
        except httpx.TimeoutException as exc:
            raise CompanyLookupUnavailable("Délai dépassé.") from exc
        except httpx.HTTPError as exc:
            raise CompanyLookupUnavailable(str(exc)) from exc

        if response.status_code == 404:
            raise CompanyLookupNotFound(siret)
        if response.status_code >= 500:
            raise CompanyLookupUnavailable(f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise CompanyLookupUnavailable(f"HTTP {response.status_code}")

        data = response.json()
        results = data.get("results", [])
        if not results:
            raise CompanyLookupNotFound(siret)

        entreprise = results[0]
        siege = entreprise.get("siege", {})

        return CompanyLookupResult(
            siret=siege.get("siret", siret),
            siren=entreprise.get("siren", siret[:9]),
            denomination=entreprise.get("nom_complet") or entreprise.get("nom_raison_sociale", ""),
            forme_juridique=entreprise.get("nature_juridique"),
            code_naf=entreprise.get("activite_principale"),
            libelle_naf=entreprise.get("libelle_activite_principale"),
            adresse_ligne1=siege.get("adresse", ""),
            code_postal=siege.get("code_postal", ""),
            commune=siege.get("libelle_commune", ""),
            tranche_effectif=entreprise.get("tranche_effectif_salarie"),
            date_creation=entreprise.get("date_creation"),
        )

    def _get_with_retry(self, siret: str) -> httpx.Response:
        """Un seul retry, sur erreur réseau ou 5xx, 300 ms de backoff. Jamais sur 404."""
        last_exc: httpx.HTTPError | None = None
        for attempt in range(2):
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    response = client.get(BASE_URL, params={"q": siret, "page": 1, "per_page": 1})
                if response.status_code == 404 or response.status_code < 500:
                    return response
                if attempt == 0:
                    import time

                    time.sleep(0.3)
                    continue
                return response
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 0:
                    import time

                    time.sleep(0.3)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise CompanyLookupUnavailable("Échec inattendu.")
