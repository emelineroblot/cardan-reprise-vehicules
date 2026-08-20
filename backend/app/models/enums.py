"""Enums Python — décision E (plan.md § 4).

Chaque colonne d'état en base est `VARCHAR` + `CHECK` (une valeur s'ajoute par un simple
`DROP`/`ADD CONSTRAINT`). La vérité fonctionnelle vit ici, côté Python ; la contrainte `CHECK`
n'est qu'un filet. Toujours dériver la liste de valeurs `CHECK` depuis ces enums pour éviter
toute divergence entre le modèle Python et la contrainte SQL.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    OPERATRICE = "operatrice"
    CHAUFFEUR = "chauffeur"
    ADMINISTRATEUR = "administrateur"
    ATELIER = "atelier"


class TypeFlotte(StrEnum):
    TAXI = "taxi"
    AMBULANCE = "ambulance"
    TRANSPORT = "transport"
    AUTO_ECOLE = "auto_ecole"
    LOCATION = "location"
    AUTRE = "autre"


class SourceEnrichissement(StrEnum):
    API = "api"
    CACHE = "cache"
    DEMO = "demo"
    MANUEL = "manuel"


class CacheSource(StrEnum):
    API = "api"
    DEMO = "demo"


class VehicleState(StrEnum):
    BROUILLON = "BROUILLON"
    A_PLANIFIER = "A_PLANIFIER"
    AFFECTE = "AFFECTE"
    RDV_PLANIFIE = "RDV_PLANIFIE"
    CONTROLE_EN_COURS = "CONTROLE_EN_COURS"
    TRAVAUX_REQUIS = "TRAVAUX_REQUIS"
    TRAVAUX_EN_COURS = "TRAVAUX_EN_COURS"
    TRAVAUX_TERMINES = "TRAVAUX_TERMINES"
    ACHAT_VALIDE = "ACHAT_VALIDE"
    REFUSE = "REFUSE"
    ANNULE = "ANNULE"


TERMINAL_STATES: frozenset[VehicleState] = frozenset(
    {VehicleState.ACHAT_VALIDE, VehicleState.REFUSE, VehicleState.ANNULE}
)


class Energie(StrEnum):
    ESSENCE = "essence"
    DIESEL = "diesel"
    HYBRIDE = "hybride"
    ELECTRIQUE = "electrique"
    GPL = "gpl"
    AUTRE = "autre"


class Boite(StrEnum):
    MANUELLE = "manuelle"
    AUTOMATIQUE = "automatique"


class RefusMotif(StrEnum):
    ETAT_MECANIQUE = "etat_mecanique"
    CARROSSERIE = "carrosserie"
    KILOMETRAGE = "kilometrage"
    PRIX = "prix"
    VENDEUR_RETRACTE = "vendeur_retracte"
    AUTRE = "autre"


class DuplicateVerdict(StrEnum):
    DUPLICATE = "duplicate"
    NOT_DUPLICATE = "not_duplicate"


class MissionState(StrEnum):
    AFFECTEE = "affectee"
    ACCEPTEE = "acceptee"
    RDV_PLANIFIE = "rdv_planifie"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"
    ANNULEE = "annulee"


class ChecklistCategorie(StrEnum):
    EXTERIEUR = "exterieur"
    INTERIEUR = "interieur"
    MECANIQUE = "mecanique"
    DOCUMENTS = "documents"
    SECURITE = "securite"


class ResponseType(StrEnum):
    OK_KO = "ok_ko"
    NOTE_1_5 = "note_1_5"
    TEXTE = "texte"
    NUMERIQUE = "numerique"


class EtatGeneral(StrEnum):
    BON = "bon"
    MOYEN = "moyen"
    MAUVAIS = "mauvais"


class InspectionConclusion(StrEnum):
    ACHAT_DIRECT = "achat_direct"
    TRAVAUX_REQUIS = "travaux_requis"
    REFUS = "refus"


class PhotoAngle(StrEnum):
    FACE_AVANT = "face_avant"
    TROIS_QUARTS_AVANT_GAUCHE = "trois_quarts_avant_gauche"
    PROFIL_GAUCHE = "profil_gauche"
    TROIS_QUARTS_ARRIERE_GAUCHE = "trois_quarts_arriere_gauche"
    FACE_ARRIERE = "face_arriere"
    TROIS_QUARTS_ARRIERE_DROIT = "trois_quarts_arriere_droit"
    PROFIL_DROIT = "profil_droit"
    TROIS_QUARTS_AVANT_DROIT = "trois_quarts_avant_droit"
    INTERIEUR_AVANT = "interieur_avant"
    INTERIEUR_ARRIERE = "interieur_arriere"
    COFFRE = "coffre"
    COMPTEUR = "compteur"
    DEFAUT = "defaut"


class PhotoPhase(StrEnum):
    CONTROLE = "controle"
    AVANT_TRAVAUX = "avant_travaux"
    APRES_TRAVAUX = "apres_travaux"


class UploadState(StrEnum):
    EN_ATTENTE = "en_attente"
    ENVOYEE = "envoyee"
    ECHOUEE = "echouee"


class WorkOrderType(StrEnum):
    CARROSSERIE = "carrosserie"
    MECANIQUE = "mecanique"
    NETTOYAGE = "nettoyage"
    PNEUMATIQUES = "pneumatiques"
    AUTRE = "autre"


class WorkOrderState(StrEnum):
    DEMANDE = "demande"
    EN_COURS = "en_cours"
    TERMINE = "termine"
    ANNULE = "annule"


class WorkOrderLineCategorie(StrEnum):
    PIECE = "piece"
    MAIN_OEUVRE = "main_oeuvre"
    SOUS_TRAITANCE = "sous_traitance"
    CONSOMMABLE = "consommable"


class VehicleCostType(StrEnum):
    TRANSPORT = "transport"
    CARBURANT = "carburant"
    ADMINISTRATIF = "administratif"
    REMISE_EN_ETAT_EXTERNE = "remise_en_etat_externe"
    AUTRE = "autre"


class DemoResetStatus(StrEnum):
    SUCCES = "succes"
    ECHEC = "echec"


def check_in(*values: StrEnum) -> str:
    """Construit la liste `'v1','v2',...` pour une contrainte `CHECK(col IN (...))`."""
    return ", ".join(f"'{v.value}'" for v in values)
