"""Model registry: importing this module registers every table on ``Base.metadata``.

Alembic (migrations/env.py) and the test harness import it; application code imports
models from their own module.
"""

from app.core.audit import AuditLog
from app.core.files import StoredFile
from app.core.jobs import Job
from app.core.models import Base
from app.core.numbering import DocumentNumberConfig, DocumentSequence
from app.modules.auth.models import RefreshToken, User, UserRole, UserScope
from app.modules.boq.models import Boq, BoqImport, BoqLine, BoqMappingTemplate, BoqRevision
from app.modules.inventory.models import (
    InventoryLocation,
    LedgerEntry,
    StockBalance,
    StockReservation,
)
from app.modules.org.models import BuildLot, Division, Module, PcbAssembly, Project, SerialUnit
from app.modules.parts.models import Part, PartPreferredVendor
from app.modules.procurement.models import (
    GoodsReceipt,
    GrnLine,
    PoLine,
    PoLineAllocation,
    PrLine,
    PurchaseOrder,
    PurchaseRequisition,
    Vendor,
    VendorReturn,
)
from app.modules.production.models import (
    StageProgress,
    StageTemplate,
    StageTemplateStep,
    WorkOrder,
    WorkOrderStage,
)
from app.modules.qc.models import Ncr, QcInspection, QcResult, QcTemplate, QcTemplateItem
from app.modules.reports.models import DesignEvaluation, DocumentDraft, QcReport
from app.modules.settings.models import CompanySettings

__all__ = [
    "AuditLog",
    "Base",
    "Boq",
    "BoqImport",
    "BoqLine",
    "BoqMappingTemplate",
    "BoqRevision",
    "BuildLot",
    "CompanySettings",
    "DesignEvaluation",
    "Division",
    "DocumentDraft",
    "DocumentNumberConfig",
    "DocumentSequence",
    "GoodsReceipt",
    "GrnLine",
    "InventoryLocation",
    "Job",
    "LedgerEntry",
    "Module",
    "Ncr",
    "Part",
    "PartPreferredVendor",
    "PcbAssembly",
    "PoLine",
    "PoLineAllocation",
    "PrLine",
    "Project",
    "PurchaseOrder",
    "PurchaseRequisition",
    "QcInspection",
    "QcReport",
    "QcResult",
    "QcTemplate",
    "QcTemplateItem",
    "RefreshToken",
    "SerialUnit",
    "StageProgress",
    "StageTemplate",
    "StageTemplateStep",
    "StockBalance",
    "StockReservation",
    "StoredFile",
    "User",
    "UserRole",
    "UserScope",
    "Vendor",
    "VendorReturn",
    "WorkOrder",
    "WorkOrderStage",
]
