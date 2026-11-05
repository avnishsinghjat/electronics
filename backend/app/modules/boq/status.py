"""BOQ line quantities and status: the single source of truth (CLAUDE.md).

    required_qty = qty_per_unit x build_qty x (1 + attrition%)   (rounded UP)
    shortfall    = max(required - ordered, 0)    -> "To order"
    pending_rcpt = max(ordered - received, 0)    -> "Awaiting delivery"

Status, in priority order:
    Not required        required is 0 (DNP line or zero quantity)
    Issued              issued   >= required
    Received            received >= required
    Partially received  received >  0
    Ordered             ordered  >= required
    Partially ordered   ordered  >  0
    Not ordered

Every screen and report (tracker, dashboards, QC report) calls this module; the frontend
never recomputes it.
"""

import enum
import math
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.modules.boq.importer import COUNTABLE_UNITS

ZERO = Decimal(0)


class LineStatus(enum.StrEnum):
    NOT_REQUIRED = "Not required"
    NOT_ORDERED = "Not ordered"
    PARTIALLY_ORDERED = "Partially ordered"
    ORDERED = "Ordered"
    PARTIALLY_RECEIVED = "Partially received"
    RECEIVED = "Received"
    ISSUED = "Issued"


def required_qty(
    qty_per_unit: Decimal,
    build_qty: int,
    attrition_pct: Decimal,
    *,
    unit: str = "pcs",
    dnp: bool = False,
) -> Decimal:
    """Rounded up to whole units for countable units (pcs, nos...); to 0.01 otherwise
    (metres of wire, grams of paste)."""
    if dnp or qty_per_unit <= 0 or build_qty <= 0:
        return ZERO
    raw = (
        Decimal(qty_per_unit)
        * Decimal(build_qty)
        * (Decimal(1) + Decimal(attrition_pct) / Decimal(100))
    )
    if unit.lower() in COUNTABLE_UNITS:
        return Decimal(math.ceil(raw))
    return raw.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class LineQuantities:
    required: Decimal
    ordered: Decimal
    received: Decimal
    issued: Decimal
    shortfall: Decimal
    pending_receipt: Decimal
    status: LineStatus

    @property
    def fully_received(self) -> bool:
        return self.status in (LineStatus.RECEIVED, LineStatus.ISSUED, LineStatus.NOT_REQUIRED)


def line_status(
    required: Decimal, ordered: Decimal, received: Decimal, issued: Decimal
) -> LineStatus:
    if required <= 0:
        return LineStatus.NOT_REQUIRED
    if issued >= required:
        return LineStatus.ISSUED
    if received >= required:
        return LineStatus.RECEIVED
    if received > 0:
        return LineStatus.PARTIALLY_RECEIVED
    if ordered >= required:
        return LineStatus.ORDERED
    if ordered > 0:
        return LineStatus.PARTIALLY_ORDERED
    return LineStatus.NOT_ORDERED


def quantities(
    required: Decimal, ordered: Decimal = ZERO, received: Decimal = ZERO, issued: Decimal = ZERO
) -> LineQuantities:
    return LineQuantities(
        required=required,
        ordered=ordered,
        received=received,
        issued=issued,
        shortfall=max(required - ordered, ZERO),
        pending_receipt=max(ordered - received, ZERO),
        status=line_status(required, ordered, received, issued),
    )
