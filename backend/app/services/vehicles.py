"""Service véhicules — référence, dédoublonnage (décision A) et transitions (§ 5.3).

Regroupe la logique métier appelée par `app/api/v1/vehicles.py` et `duplicates.py`, sans
dépendance FastAPI (testable en isolation si besoin d'intégration légère).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.company import Company
from app.models.enums import UserRole, VehicleState
from app.models.inspection import Inspection
from app.models.user import AppUser
from app.models.vehicle import DuplicateReview, Vehicle
from app.models.work_order import WorkOrder
from app.schemas.vehicle import VehicleCreate, VehicleDraftIn
from app.services import missions as missions_service
from app.services import notifications as notifications_service
from app.services.audit import write_vehicle_transition
from app.services.dedup import VehicleDraft, score_candidate
from app.services.normalize import normalize_immatriculation, normalize_modele, normalize_vin
from app.services.state_machine import (
    InvalidTransitionError,
    TransitionContext,
    apply_transition,
)

DEDUP_DATE_WINDOW_DAYS = 90


def generate_reference(db: Session) -> str:
    """`VH-{année}-{numéro}` — consomme la séquence dédiée `vehicle_reference_seq` (migration)."""
    seq_value = db.scalar(text("SELECT nextval('vehicle_reference_seq')"))
    year = datetime.now(UTC).year
    return f"VH-{year}-{int(seq_value):06d}"


def _to_vehicle_draft(
    row: Vehicle | VehicleDraftIn, *, vin_norm: str | None = None, immat_norm: str | None = None
) -> VehicleDraft:
    if isinstance(row, Vehicle):
        return VehicleDraft(
            marque=row.marque,
            modele=row.modele,
            version=row.version,
            vin_normalise=row.vin_normalise,
            immat_normalisee=row.immat_normalisee,
            date_mise_en_circulation=row.date_mise_en_circulation,
            kilometrage=row.kilometrage,
            energie=row.energie,
            date_proposition=row.date_proposition,
            state=row.state,
            refus_commentaire=row.refus_commentaire,
        )
    return VehicleDraft(
        marque=row.marque,
        modele=row.modele,
        version=row.version,
        vin_normalise=vin_norm,
        immat_normalisee=immat_norm,
        date_mise_en_circulation=row.date_mise_en_circulation,
        kilometrage=row.kilometrage,
        energie=row.energie,
        date_proposition=row.date_proposition,
        state=None,
        refus_commentaire=None,
    )


def find_candidates(
    db: Session,
    *,
    company_id: UUID,
    date_proposition: date,
    intake_batch_id: UUID | None,
    exclude_vehicle_id: UUID | None = None,
) -> list[Vehicle]:
    """Étape 1 (blocage) — même société, date à ±90 j, `intake_batch_id` différent.

    Les membres d'un même lot ne sont **jamais** comparés entre eux : c'est la réponse
    structurelle au faux positif de flotte (décision A, étape 5).
    """
    window_start = date_proposition - timedelta(days=DEDUP_DATE_WINDOW_DAYS)
    window_end = date_proposition + timedelta(days=DEDUP_DATE_WINDOW_DAYS)

    stmt = select(Vehicle).where(
        Vehicle.company_id == company_id,
        Vehicle.date_proposition >= window_start,
        Vehicle.date_proposition <= window_end,
    )
    if intake_batch_id is not None:
        stmt = stmt.where(
            (Vehicle.intake_batch_id.is_(None)) | (Vehicle.intake_batch_id != intake_batch_id)
        )
    if exclude_vehicle_id is not None:
        stmt = stmt.where(Vehicle.id != exclude_vehicle_id)

    return list(db.execute(stmt).scalars().all())


def check_exact_duplicate(
    db: Session,
    vin_normalise: str | None,
    immat_normalisee: str | None,
    *,
    exclude_vehicle_id: UUID | None = None,
) -> tuple[Vehicle, str] | None:
    """Étape 0 — collision VIN/immatriculation. Garantie par l'index unique partiel côté base ;
    ce contrôle applicatif évite un aller-retour d'erreur inutile dans le cas non concurrent.

    Renvoie `(véhicule, champ)` — le champ ayant réellement matché est renvoyé explicitement :
    comparer `exact.vin_normalise == vin_normalise` après coup est un piège dès que les deux
    valent `None` (`None == None` est vrai), ce qui mislabelle une collision immatriculation.

    `exclude_vehicle_id` — utilisé par `PATCH /vehicles/{id}` : la fiche modifiée ne doit pas se
    matcher elle-même (revue § 🟠 « PATCH ne rejoue pas le contrôle de doublon exact »).
    """
    if vin_normalise:
        stmt = select(Vehicle).where(Vehicle.vin_normalise == vin_normalise)
        if exclude_vehicle_id is not None:
            stmt = stmt.where(Vehicle.id != exclude_vehicle_id)
        existing = db.scalar(stmt)
        if existing is not None:
            return existing, "vin"
    if immat_normalisee:
        stmt = select(Vehicle).where(Vehicle.immat_normalisee == immat_normalisee)
        if exclude_vehicle_id is not None:
            stmt = stmt.where(Vehicle.id != exclude_vehicle_id)
        existing = db.scalar(stmt)
        if existing is not None:
            return existing, "immatriculation"
    return None


def run_duplicate_check(
    db: Session, draft: VehicleDraftIn, *, exclude_vehicle_id: UUID | None = None
) -> dict:
    """Décision A complète : exact + candidats scorés (probable/similar), avec explication."""
    vin_norm = normalize_vin(draft.vin)
    immat_norm = normalize_immatriculation(draft.immatriculation)

    exact_matches = []
    exact_result = check_exact_duplicate(db, vin_norm, immat_norm)
    if exact_result is not None and exact_result[0].id != exclude_vehicle_id:
        exact_vehicle, champ = exact_result
        exact_matches.append(
            {
                "champ": champ,
                "vehicle_id": str(exact_vehicle.id),
                "reference": exact_vehicle.reference,
            }
        )

    candidates = find_candidates(
        db,
        company_id=draft.company_id,
        date_proposition=draft.date_proposition,
        intake_batch_id=draft.intake_batch_id,
        exclude_vehicle_id=exclude_vehicle_id,
    )

    draft_vehicle = _to_vehicle_draft(draft, vin_norm=vin_norm, immat_norm=immat_norm)

    probable = []
    similar = []
    for candidate in candidates:
        review = None
        if exclude_vehicle_id is not None:
            pair_a, pair_b = sorted((candidate.id, exclude_vehicle_id))
            review = db.scalar(
                select(DuplicateReview).where(
                    DuplicateReview.vehicle_a_id == pair_a,
                    DuplicateReview.vehicle_b_id == pair_b,
                )
            )
        if review is not None and review.verdict == "not_duplicate":
            continue  # un verdict not_duplicate est définitif (décision A, étape 5)

        verdict = score_candidate(draft_vehicle, _to_vehicle_draft(candidate))
        item = {
            "vehicle_id": str(candidate.id),
            "reference": candidate.reference,
            "marque": candidate.marque,
            "modele": candidate.modele,
            "version": candidate.version,
            # Champs de comparaison côte à côte (correction dev-frontend, jalon J1) — chacun
            # justifie une composante du score affichée à l'opératrice : `energie` → s_energie,
            # `kilometrage` → s_km, `vin`/`immatriculation` → l'exclusion dure de l'étape 2.
            "energie": candidate.energie,
            "vin": candidate.vin,
            "immatriculation": candidate.immatriculation,
            "kilometrage": candidate.kilometrage,
            "date_mise_en_circulation": (
                candidate.date_mise_en_circulation.isoformat()
                if candidate.date_mise_en_circulation
                else None
            ),
            "date_proposition": candidate.date_proposition.isoformat(),
            "created_at": candidate.created_at.isoformat(),
            "state": candidate.state,
            "refus_motif": candidate.refus_motif,
            "refus_commentaire": candidate.refus_commentaire,
            "score": round(verdict.score, 4),
            # Nommé `features`, pas `components` : identique au champ attendu par
            # `POST /duplicate-reviews` (plan.md § 5.1 : `duplicate_review.features JSONB`) —
            # le front renvoie tel quel ce qu'il a reçu (revue § 🔴, point 4).
            "features": verdict.components.as_dict(),
        }
        if verdict.is_probable:
            probable.append(item)
        elif verdict.is_similar:
            similar.append(item)

    return {"exact": exact_matches, "probable": probable, "similar": similar}


def create_vehicle(db: Session, payload: VehicleCreate, user: AppUser) -> Vehicle:
    if db.get(Company, payload.company_id) is None:
        raise ApiError("not_found", "Société introuvable.")

    vin_norm = normalize_vin(payload.vin)
    immat_norm = normalize_immatriculation(payload.immatriculation)
    modele_norm = normalize_modele(payload.marque, payload.modele, payload.version)

    exact_result = check_exact_duplicate(db, vin_norm, immat_norm)
    if exact_result is not None:
        exact, champ = exact_result
        raise ApiError(
            "duplicate_exact",
            f"Ce {champ} existe déjà.",
            details={"champ": champ, "vehicle_id": str(exact.id), "reference": exact.reference},
        )

    if not payload.force_create:
        check = run_duplicate_check(db, payload)
        if check["probable"]:
            raise ApiError(
                "duplicate_probable",
                "Un véhicule très proche existe déjà — vérifiez avant de continuer.",
                details=check,
            )

    reference = generate_reference(db)
    vehicle = Vehicle(
        id=uuid4(),
        reference=reference,
        company_id=payload.company_id,
        intake_batch_id=payload.intake_batch_id,
        state=VehicleState.BROUILLON.value,
        marque=payload.marque,
        modele=payload.modele,
        version=payload.version,
        modele_normalise=modele_norm,
        energie=payload.energie,
        boite=payload.boite,
        couleur=payload.couleur,
        vin=payload.vin,
        vin_normalise=vin_norm,
        immatriculation=payload.immatriculation,
        immat_normalisee=immat_norm,
        date_mise_en_circulation=payload.date_mise_en_circulation,
        kilometrage=payload.kilometrage,
        date_proposition=payload.date_proposition,
        prix_achat_negocie_cents=payload.prix_achat_negocie_cents,
        valeur_revente_estimee_cents=payload.valeur_revente_estimee_cents,
        frais_transport_cents=payload.frais_transport_cents,
        commentaire=payload.commentaire,
        created_by_id=user.id,
    )
    db.add(vehicle)
    db.flush()

    write_vehicle_transition(
        db,
        vehicle_id=vehicle.id,
        from_state=None,
        to_state=VehicleState.BROUILLON.value,
        actor_id=user.id,
        actor_role=user.role,
        reason="Création de la fiche",
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def _parse_iso_datetime_field(payload: dict, field: str) -> datetime | None:
    """Parse `payload[field]` en `datetime` tz-aware, ou `None` si absent. Levée `ApiError
    validation_error` (jamais un 500 brut) sur une valeur malformée — `payload` est un dict
    client libre (revue § 🟡 J1). Partagée entre la garde d'automate (`build_transition_context`)
    et les effets de bord (`transition_vehicle`) pour ne parser `rdv_at` qu'à un seul endroit."""
    raw = payload.get(field)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError) as exc:
        raise ApiError(
            "validation_error", f"payload.{field} invalide (date ISO-8601 attendue)."
        ) from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def build_transition_context(
    db: Session, vehicle: Vehicle, user: AppUser, payload: dict
) -> TransitionContext:
    driver_target_active = False
    driver_id = payload.get("driver_id")
    if driver_id:
        try:
            driver_uuid = UUID(driver_id) if isinstance(driver_id, str) else driver_id
        except (ValueError, TypeError, AttributeError) as exc:
            # `payload` est un dict client libre (revue § 🟡) : une valeur malformée doit rester
            # un 422 propre, jamais un 500 brut.
            raise ApiError(
                "validation_error", "payload.driver_id invalide (UUID attendu)."
            ) from exc
        driver = db.get(AppUser, driver_uuid)
        driver_target_active = bool(
            driver and driver.role == UserRole.CHAUFFEUR.value and driver.is_active
        )

    rdv_at = _parse_iso_datetime_field(payload, "rdv_at")
    rdv_at_is_future = rdv_at is not None and rdv_at > datetime.now(UTC)

    inspection_ok = (
        db.scalar(
            select(Inspection.id).where(
                Inspection.vehicle_id == vehicle.id, Inspection.submitted_at.is_not(None)
            )
        )
        is not None
    )

    open_work_orders = list(
        db.execute(select(WorkOrder).where(WorkOrder.vehicle_id == vehicle.id)).scalars().all()
    )
    has_work_order_en_demande = any(w.state == "demande" for w in open_work_orders)
    all_closed_with_cost = bool(open_work_orders) and all(
        w.state in ("termine", "annule") for w in open_work_orders
    )

    return TransitionContext(
        assigned_driver_id=str(vehicle.assigned_driver_id) if vehicle.assigned_driver_id else None,
        actor_id=str(user.id),
        actor_role=user.role,
        is_assigned_driver=vehicle.assigned_driver_id == user.id,
        is_owner_operatrice=vehicle.created_by_id == user.id,
        rdv_at_is_future=rdv_at_is_future,
        inspection_submitted_with_required_angles=inspection_ok,
        prix_achat_negocie_present=payload.get("prix_achat_negocie_cents") is not None
        or vehicle.prix_achat_negocie_cents is not None,
        refus_motif_present=payload.get("refus_motif") is not None
        or vehicle.refus_motif is not None,
        reason_present=bool(payload.get("reason")),
        driver_target_is_active_chauffeur=driver_target_active,
        has_work_order_en_demande=has_work_order_en_demande,
        all_work_orders_closed_with_cost_line=all_closed_with_cost,
        active_work_orders_count=len(open_work_orders),
    )


def transition_vehicle(
    db: Session,
    vehicle: Vehicle,
    to_state: str,
    user: AppUser,
    reason: str | None,
    payload: dict | None,
) -> Vehicle:
    payload = dict(payload or {})
    if reason:
        payload["reason"] = reason

    try:
        from_state = VehicleState(vehicle.state)
        target_state = VehicleState(to_state)
    except ValueError as exc:
        raise ApiError("validation_error", "État inconnu.") from exc

    ctx = build_transition_context(db, vehicle, user, payload)

    try:
        apply_transition(from_state, target_state, ctx)
    except InvalidTransitionError as exc:
        raise ApiError(
            "invalid_transition",
            "Cette transition n'est pas autorisée dans ce contexte.",
            details={"allowed": exc.allowed},
        ) from exc

    old_state = vehicle.state

    # Effets de bord sur `mission` (plan.md § 5.3, colonne « Effet ») — la mission n'est jamais
    # le déclencheur, seulement une conséquence de la transition véhicule déjà validée ci-dessus
    # (« un seul point d'entrée », § 5.3). `pending_notification` est envoyée en push (best
    # effort) *après* le commit principal, plus bas — un échec réseau ne doit jamais annuler une
    # affectation déjà actée (brief J2, arbitrage « notifications »).
    pending_notification = None

    if target_state == VehicleState.AFFECTE and payload.get("driver_id"):
        # Couvre à la fois `A_PLANIFIER → AFFECTE` (première affectation) et `AFFECTE → AFFECTE`
        # (réaffectation) : dans les deux cas, une éventuelle mission active existante est
        # annulée avant d'en créer une nouvelle — sans quoi l'index unique partiel
        # `uq_mission_vehicle_active` refuserait l'insertion (plan.md § 5.1).
        driver_id = UUID(payload["driver_id"])
        previous_mission = missions_service.get_active_mission(db, vehicle.id)
        if previous_mission is not None:
            missions_service.cancel_mission(db, previous_mission)
        vehicle.assigned_driver_id = driver_id
        new_mission = missions_service.create_mission(
            db, vehicle, driver_id=driver_id, assigned_by_id=user.id
        )
        pending_notification = notifications_service.notify_mission_assigned(
            db, driver_id=driver_id, vehicle=vehicle, mission=new_mission
        )
    elif target_state == VehicleState.RDV_PLANIFIE:
        mission = missions_service.get_active_mission(db, vehicle.id)
        if mission is not None:
            missions_service.mark_rdv(
                db,
                mission,
                rdv_at=_parse_iso_datetime_field(payload, "rdv_at"),
                rdv_adresse=payload.get("rdv_adresse"),
                rdv_contact_nom=payload.get("rdv_contact_nom"),
                rdv_contact_telephone=payload.get("rdv_contact_telephone"),
            )
    elif target_state == VehicleState.CONTROLE_EN_COURS:
        mission = missions_service.get_active_mission(db, vehicle.id)
        if mission is not None:
            missions_service.start_control(db, mission)
    elif target_state in (
        VehicleState.TRAVAUX_REQUIS,
        VehicleState.ACHAT_VALIDE,
        VehicleState.REFUSE,
    ):
        # Les trois sorties de `CONTROLE_EN_COURS` clôturent la mission (le passage sur place du
        # chauffeur est terminé) ; si l'état atteint vient plutôt de `TRAVAUX_TERMINES` (J3), la
        # mission est déjà `terminee` et `get_active_mission` renvoie `None` — no-op naturel.
        mission = missions_service.get_active_mission(db, vehicle.id)
        if mission is not None:
            missions_service.complete_mission(db, mission)
    elif target_state == VehicleState.ANNULE:
        mission = missions_service.get_active_mission(db, vehicle.id)
        if mission is not None:
            missions_service.cancel_mission(db, mission)

    if payload.get("refus_motif"):
        vehicle.refus_motif = payload["refus_motif"]
    if payload.get("refus_commentaire"):
        vehicle.refus_commentaire = payload["refus_commentaire"]
    if payload.get("prix_achat_negocie_cents") is not None:
        vehicle.prix_achat_negocie_cents = payload["prix_achat_negocie_cents"]

    vehicle.state = target_state.value
    vehicle.state_changed_at = datetime.now(UTC)
    db.flush()

    write_vehicle_transition(
        db,
        vehicle_id=vehicle.id,
        from_state=old_state,
        to_state=target_state.value,
        actor_id=user.id,
        actor_role=user.role,
        reason=reason,
        payload=payload or None,
    )
    db.commit()
    db.refresh(vehicle)

    if pending_notification is not None:
        notifications_service.dispatch_pending_push(db, pending_notification)

    return vehicle
