"""Every constraint group rejects bad data at the database level."""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import integrity_error_info
from app.modules.inventory.models import LedgerEntry, StockBalance
from app.modules.qc.models import Ncr, QcInspection, QcTemplate, QcTemplateItem
from tests.factories import (
    AssemblyFactory,
    BoqFactory,
    BoqLineFactory,
    BoqRevisionFactory,
    DivisionFactory,
    GoodsReceiptFactory,
    GrnLineFactory,
    LocationFactory,
    PartFactory,
    PoLineFactory,
    ProjectFactory,
    PurchaseOrderFactory,
    SerialFactory,
    VendorFactory,
    create,
    project_tree,
)


async def violates(
    session: AsyncSession, action: Callable[[], Awaitable[Any]], expected_code: str
) -> str | None:
    """Run ``action`` in a savepoint; assert it fails with the given error code."""
    with pytest.raises(IntegrityError) as exc_info:
        async with session.begin_nested():
            await action()
    _, code, _, details = integrity_error_info(exc_info.value)
    assert code == expected_code, exc_info.value
    return details["constraint"]


# --- unique constraints -----------------------------------------------------------


async def test_part_mpn_manufacturer_unique_ignoring_case_and_spaces(
    db_session: AsyncSession,
) -> None:
    await create(db_session, PartFactory, mpn="GRM188R71H104KA93D", manufacturer="Murata")
    name = await violates(
        db_session,
        lambda: create(db_session, PartFactory, mpn="grm188r71h104 ka93d", manufacturer="MURATA"),
        "duplicate",
    )
    assert name == "uq_parts_mpn_manufacturer_live"


async def test_part_same_mpn_other_manufacturer_allowed(db_session: AsyncSession) -> None:
    await create(db_session, PartFactory, mpn="LM358DR", manufacturer="Texas Instruments")
    await create(db_session, PartFactory, mpn="LM358DR", manufacturer="onsemi")


async def test_soft_deleted_part_frees_its_mpn(db_session: AsyncSession) -> None:
    old = await create(db_session, PartFactory, mpn="NE555", manufacturer="TI")
    old.is_deleted = True
    await db_session.flush()
    await create(db_session, PartFactory, mpn="NE555", manufacturer="TI")


async def test_po_number_unique(db_session: AsyncSession) -> None:
    vendor = await create(db_session, VendorFactory)
    await create(db_session, PurchaseOrderFactory, number="PO-2026-0001", vendor_id=vendor.id)
    name = await violates(
        db_session,
        lambda: create(
            db_session, PurchaseOrderFactory, number="PO-2026-0001", vendor_id=vendor.id
        ),
        "duplicate",
    )
    assert name == "uq_purchase_orders_number"


async def test_serial_unique_per_assembly(db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)
    other = await create(db_session, AssemblyFactory, module_id=tree["module"].id)
    await create(db_session, SerialFactory, assembly_id=tree["assembly"].id, serial_number="SN-1")
    # Same serial on a different assembly is fine.
    await create(db_session, SerialFactory, assembly_id=other.id, serial_number="SN-1")
    name = await violates(
        db_session,
        lambda: create(
            db_session, SerialFactory, assembly_id=tree["assembly"].id, serial_number="SN-1"
        ),
        "duplicate",
    )
    assert name == "uq_serial_units_assembly_serial_live"


async def test_only_one_released_boq_revision(db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)
    boq = await create(db_session, BoqFactory, project_id=tree["project"].id)
    await create(db_session, BoqRevisionFactory, boq_id=boq.id, revision="A", status="released")
    await create(db_session, BoqRevisionFactory, boq_id=boq.id, revision="B", status="draft")
    name = await violates(
        db_session,
        lambda: create(
            db_session, BoqRevisionFactory, boq_id=boq.id, revision="C", status="released"
        ),
        "duplicate",
    )
    assert name == "uq_boq_revisions_one_released"


async def test_division_code_unique(db_session: AsyncSession) -> None:
    await create(db_session, DivisionFactory, code="DUP")
    await violates(db_session, lambda: create(db_session, DivisionFactory, code="DUP"), "duplicate")


# --- quantity checks (qty >= 0 / > 0) --------------------------------------------


async def _po_line_setup(session: AsyncSession) -> tuple[Any, Any]:
    vendor = await create(session, VendorFactory)
    po = await create(session, PurchaseOrderFactory, vendor_id=vendor.id)
    part = await create(session, PartFactory)
    return po, part


@pytest.mark.parametrize("qty", [Decimal(0), Decimal(-5)])
async def test_po_line_qty_must_be_positive(db_session: AsyncSession, qty: Decimal) -> None:
    po, part = await _po_line_setup(db_session)
    name = await violates(
        db_session,
        lambda: create(
            db_session, PoLineFactory, purchase_order_id=po.id, part_id=part.id, qty_ordered=qty
        ),
        "constraint_violation",
    )
    assert name == "ck_po_lines_qty_ordered_pos"


async def test_boq_line_qty_and_attrition_checked(db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)
    boq = await create(db_session, BoqFactory, project_id=tree["project"].id)
    rev = await create(db_session, BoqRevisionFactory, boq_id=boq.id)
    assert (
        await violates(
            db_session,
            lambda: create(
                db_session, BoqLineFactory, revision_id=rev.id, qty_per_unit=Decimal(-1)
            ),
            "constraint_violation",
        )
        == "ck_boq_lines_qty_per_unit_nonneg"
    )
    assert (
        await violates(
            db_session,
            lambda: create(
                db_session, BoqLineFactory, revision_id=rev.id, attrition_pct=Decimal(150)
            ),
            "constraint_violation",
        )
        == "ck_boq_lines_attrition_range"
    )
    # zero qty (e.g. a DNP placeholder) is allowed
    await create(db_session, BoqLineFactory, revision_id=rev.id, qty_per_unit=Decimal(0), dnp=True)


async def test_grn_line_split_must_add_up(db_session: AsyncSession) -> None:
    po, part = await _po_line_setup(db_session)
    line = await create(db_session, PoLineFactory, purchase_order_id=po.id, part_id=part.id)
    grn = await create(db_session, GoodsReceiptFactory, purchase_order_id=po.id)
    assert (
        await violates(
            db_session,
            lambda: create(
                db_session,
                GrnLineFactory,
                goods_receipt_id=grn.id,
                po_line_id=line.id,
                qty_received=Decimal(10),
                qty_accepted=Decimal(7),
                qty_rejected=Decimal(2),
            ),
            "constraint_violation",
        )
        == "ck_grn_lines_qty_parts_sum"
    )
    await create(
        db_session,
        GrnLineFactory,
        goods_receipt_id=grn.id,
        po_line_id=line.id,
        qty_received=Decimal(10),
        qty_accepted=Decimal(7),
        qty_rejected=Decimal(2),
        qty_on_hold=Decimal(1),
    )


async def test_stock_balance_cannot_go_negative(db_session: AsyncSession) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)

    async def insert_negative() -> None:
        db_session.add(StockBalance(part_id=part.id, location_id=loc.id, qty_on_hand=Decimal(-1)))
        await db_session.flush()

    assert await violates(db_session, insert_negative, "constraint_violation") == (
        "ck_stock_balances_qty_on_hand_nonneg"
    )


async def test_ledger_sign_must_match_reason(db_session: AsyncSession) -> None:
    part = await create(db_session, PartFactory)
    loc = await create(db_session, LocationFactory)

    async def bad(reason: str, qty: int) -> None:
        db_session.add(
            LedgerEntry(part_id=part.id, location_id=loc.id, qty_delta=Decimal(qty), reason=reason)
        )
        await db_session.flush()

    assert await violates(db_session, lambda: bad("GRN", -5), "constraint_violation") == (
        "ck_inventory_ledger_reason_sign"
    )
    assert await violates(db_session, lambda: bad("ISSUE", 5), "constraint_violation") == (
        "ck_inventory_ledger_reason_sign"
    )
    assert await violates(db_session, lambda: bad("ADJUST", 0), "constraint_violation") == (
        "ck_inventory_ledger_qty_delta_nonzero"
    )


# --- enum / status checks -----------------------------------------------------------


async def test_status_values_are_enforced(db_session: AsyncSession) -> None:
    division = await create(db_session, DivisionFactory)
    assert (
        await violates(
            db_session,
            lambda: create(db_session, ProjectFactory, division_id=division.id, status="exploded"),
            "constraint_violation",
        )
        == "ck_projects_status_valid"
    )


# --- date ordering ------------------------------------------------------------------


async def test_project_due_date_not_before_start(db_session: AsyncSession) -> None:
    division = await create(db_session, DivisionFactory)
    assert (
        await violates(
            db_session,
            lambda: create(
                db_session,
                ProjectFactory,
                division_id=division.id,
                start_date=date(2026, 5, 1),
                due_date=date(2026, 4, 1),
            ),
            "constraint_violation",
        )
        == "ck_projects_dates_ordered"
    )


# --- format checks ------------------------------------------------------------------


@pytest.mark.parametrize("gstin", ["27AABCS1234F1Z", "27aabcs1234f1z5", "XXAABCS1234F1Z5"])
async def test_vendor_gstin_format(db_session: AsyncSession, gstin: str) -> None:
    assert (
        await violates(
            db_session,
            lambda: create(db_session, VendorFactory, gstin=gstin),
            "constraint_violation",
        )
        == "ck_vendors_gstin_format"
    )


async def test_valid_gstin_accepted(db_session: AsyncSession) -> None:
    await create(db_session, VendorFactory, gstin="27AABCS1234F1Z5")


# --- foreign keys -------------------------------------------------------------------


async def test_foreign_keys_reject_missing_parent(db_session: AsyncSession) -> None:
    import uuid

    await violates(
        db_session,
        lambda: create(db_session, ProjectFactory, division_id=uuid.uuid4()),
        "reference_error",
    )


async def test_parent_with_children_cannot_be_hard_deleted(db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)

    async def delete_division() -> None:
        await db_session.execute(
            text("DELETE FROM divisions WHERE id = :id"), {"id": tree["division"].id}
        )

    await violates(db_session, delete_division, "reference_error")


# --- QC rules -------------------------------------------------------------------------


async def test_qc_limits_and_photo_rules(db_session: AsyncSession) -> None:
    template = QcTemplate(code="T-1", name="Visual", stage_code="reflow")
    db_session.add(template)
    await db_session.flush()

    async def item(**kw: Any) -> None:
        db_session.add(
            QcTemplateItem(
                template_id=template.id,
                seq=kw.pop("seq"),
                item_type="measurement",
                prompt="V",
                **kw,
            )
        )
        await db_session.flush()

    assert (
        await violates(
            db_session,
            lambda: item(seq=1, min_value=Decimal(5), max_value=Decimal(1)),
            "constraint_violation",
        )
        == "ck_qc_template_items_limits_ordered"
    )
    assert (
        await violates(
            db_session,
            lambda: item(seq=2, photo_required=True, min_photos=0),
            "constraint_violation",
        )
        == "ck_qc_template_items_photo_required_count"
    )


async def test_inspection_needs_a_subject(db_session: AsyncSession) -> None:
    template = QcTemplate(code="T-2", name="Final", stage_code="packing")
    db_session.add(template)
    await db_session.flush()

    async def bare() -> None:
        db_session.add(QcInspection(number="QC-X-1", template_id=template.id, stage_code="packing"))
        await db_session.flush()

    assert (
        await violates(db_session, bare, "constraint_violation") == "ck_qc_inspections_has_subject"
    )


async def test_ncr_cannot_close_without_disposition(db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)

    async def closed_ncr() -> None:
        db_session.add(
            Ncr(
                number="NCR-X-1",
                project_id=tree["project"].id,
                defect_category="bridging",
                severity="major",
                description="Bridge U1 pins 3-4",
                status="closed",
            )
        )
        await db_session.flush()

    assert (
        await violates(db_session, closed_ncr, "constraint_violation")
        == "ck_ncrs_closed_has_disposition"
    )
