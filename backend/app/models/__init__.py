"""Import de tous les modèles — nécessaire pour qu'Alembic `autogenerate` voie le schéma complet."""

from app.models.analytics import AnalyticsRefreshLog
from app.models.audit import AuditLog
from app.models.checklist import ChecklistItemTemplate, ChecklistTemplate
from app.models.company import Company, CompanyLookupCache, LookupHealth
from app.models.demo import DemoResetRun
from app.models.inspection import Inspection, InspectionItem
from app.models.intake_batch import IntakeBatch
from app.models.mission import Mission
from app.models.notification import Notification, PushSubscription
from app.models.photo import Photo
from app.models.user import AppUser
from app.models.vehicle import DuplicateReview, Vehicle, VehicleStateTransition
from app.models.vehicle_cost import VehicleCost
from app.models.work_order import WorkOrder, WorkOrderLine

__all__ = [
    "AnalyticsRefreshLog",
    "AppUser",
    "AuditLog",
    "ChecklistItemTemplate",
    "ChecklistTemplate",
    "Company",
    "CompanyLookupCache",
    "DemoResetRun",
    "DuplicateReview",
    "Inspection",
    "InspectionItem",
    "IntakeBatch",
    "LookupHealth",
    "Mission",
    "Notification",
    "Photo",
    "PushSubscription",
    "Vehicle",
    "VehicleCost",
    "VehicleStateTransition",
    "WorkOrder",
    "WorkOrderLine",
]
