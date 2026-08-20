"""Dédoublonnage approximatif — plan.md § 4 décision A.

Candidats en SQL (blocage) + scoring pondéré en Python (`rapidfuzz`), avec exclusions dures
avant tout scoring. Fonctions pures et testables sans base pour le cœur du scoring
(`score_candidate`), et une fonction d'orchestration SQL (`find_candidates`) côté service.

Seuils : ≥ 0,85 → doublon probable (bloquant) ; [0,70, 0,85[ → similitude signalée (non
bloquant) ; < 0,70 → silence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from app.services.normalize import normalize_modele

# Seuils — plan.md § 4 décision A, étape 4. Constantes nommées, commentées, couvertes par une
# table de cas de test (tests/unit/test_dedup.py).
THRESHOLD_PROBABLE = 0.85
THRESHOLD_SIMILAR = 0.70

WEIGHT_MODELE = 0.40
WEIGHT_DATE = 0.25
WEIGHT_KM = 0.20
WEIGHT_ENERGIE = 0.15

DATE_WINDOW_DAYS = 90
KM_WINDOW = 5000

# Exclusions dures (étape 2)
MAX_DATE_MISE_EN_CIRCULATION_ECART_DAYS = 365
MAX_KILOMETRAGE_ECART = 5000
MIN_MARQUE_SIMILARITY = 0.90

# Bonus métier : le candidat est dans un état terminal REFUSE/ANNULE — c'est précisément le
# scénario que l'opératrice a besoin de voir (« déjà refusé il y a 6 semaines »).
TERMINAL_STATES_FOR_BONUS = frozenset({"REFUSE", "ANNULE"})
BONUS_TERMINAL_STATE = 0.05


@dataclass(frozen=True)
class VehicleDraft:
    """Vue minimale d'un véhicule (brouillon ou existant) nécessaire au scoring."""

    marque: str
    modele: str
    version: str | None
    vin_normalise: str | None
    immat_normalisee: str | None
    date_mise_en_circulation: date | None
    kilometrage: int | None
    energie: str | None
    date_proposition: date
    state: str | None = None
    refus_commentaire: str | None = None


@dataclass(frozen=True)
class ScoreComponents:
    s_modele: float
    s_date: float
    s_km: float
    s_energie: float
    bonus_terminal: float

    def as_dict(self) -> dict[str, float]:
        return {
            "s_modele": round(self.s_modele, 4),
            "s_date": round(self.s_date, 4),
            "s_km": round(self.s_km, 4),
            "s_energie": round(self.s_energie, 4),
            "bonus_terminal": round(self.bonus_terminal, 4),
        }


@dataclass(frozen=True)
class DedupVerdict:
    excluded: bool
    exclusion_reason: str | None
    score: float
    components: ScoreComponents = field(default_factory=lambda: ScoreComponents(0, 0, 0, 0, 0))

    @property
    def is_probable(self) -> bool:
        return not self.excluded and self.score >= THRESHOLD_PROBABLE

    @property
    def is_similar(self) -> bool:
        return not self.excluded and THRESHOLD_SIMILAR <= self.score < THRESHOLD_PROBABLE

    @property
    def is_silent(self) -> bool:
        return self.excluded or self.score < THRESHOLD_SIMILAR


def _hard_exclusion(a: VehicleDraft, b: VehicleDraft) -> str | None:
    """Étape 2 — un candidat est éliminé sans scoring si l'une de ces conditions est vraie.

    C'est cette étape qui neutralise le cas des 5 Kangoo : dès que l'opératrice saisit
    l'immatriculation ou le kilométrage, les fiches deviennent mutuellement inéligibles.
    """
    if a.vin_normalise and b.vin_normalise and a.vin_normalise != b.vin_normalise:
        return "vin_different"
    if a.immat_normalisee and b.immat_normalisee and a.immat_normalisee != b.immat_normalisee:
        return "immatriculation_different"
    if a.date_mise_en_circulation and b.date_mise_en_circulation:
        ecart = abs((a.date_mise_en_circulation - b.date_mise_en_circulation).days)
        if ecart > MAX_DATE_MISE_EN_CIRCULATION_ECART_DAYS:
            return "date_mise_en_circulation_ecart_trop_grand"
    if (
        a.kilometrage is not None
        and b.kilometrage is not None
        and abs(a.kilometrage - b.kilometrage) > MAX_KILOMETRAGE_ECART
    ):
        return "kilometrage_ecart_trop_grand"
    marque_similarity = fuzz.ratio(a.marque.strip().lower(), b.marque.strip().lower()) / 100
    if marque_similarity < MIN_MARQUE_SIMILARITY:
        return "marque_differente"
    return None


def score_candidate(a: VehicleDraft, b: VehicleDraft) -> DedupVerdict:
    """Étapes 2 à 4 de la décision A : exclusions dures puis score composite."""
    exclusion = _hard_exclusion(a, b)
    if exclusion is not None:
        return DedupVerdict(excluded=True, exclusion_reason=exclusion, score=0.0)

    norm_a = normalize_modele(a.marque, a.modele, a.version)
    norm_b = normalize_modele(b.marque, b.modele, b.version)
    s_modele = fuzz.token_set_ratio(norm_a, norm_b) / 100

    delta_jours = abs((a.date_proposition - b.date_proposition).days)
    s_date = max(0.0, 1 - delta_jours / DATE_WINDOW_DAYS)

    if a.kilometrage is not None and b.kilometrage is not None:
        s_km = 1 - min(1.0, abs(a.kilometrage - b.kilometrage) / KM_WINDOW)
    else:
        s_km = 0.5  # neutre — l'un des deux kilométrages manque

    if a.energie and b.energie:
        s_energie = 1.0 if a.energie == b.energie else 0.0
    elif a.energie or b.energie:
        s_energie = 0.5
    else:
        s_energie = 0.5

    score = (
        WEIGHT_MODELE * s_modele
        + WEIGHT_DATE * s_date
        + WEIGHT_KM * s_km
        + WEIGHT_ENERGIE * s_energie
    )

    bonus = 0.0
    if b.state in TERMINAL_STATES_FOR_BONUS:
        bonus = BONUS_TERMINAL_STATE
        score += bonus

    score = min(1.0, score)

    return DedupVerdict(
        excluded=False,
        exclusion_reason=None,
        score=score,
        components=ScoreComponents(s_modele, s_date, s_km, s_energie, bonus),
    )
