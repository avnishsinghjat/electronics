import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.modules.auth.deps import require
from app.modules.auth.service import Principal
from app.modules.procurement import pdf, service, tracker, views
from app.modules.procurement.schemas import (
    GrnCreate,
    GrnDetail,
    GrnOut,
    GrnPatch,
    HoldResolution,
    NoteIn,
    PendingLine,
    PoCreate,
    PoDetail,
    PoLinePatch,
    PoOut,
    PoRef,
    PoUpdate,
    PrDecision,
    PrDetail,
    PrFromShortfall,
    PrOut,
    PrUpdate,
    ReturnOut,
    ReturnUpdate,
    TrackerOut,
    VendorCreate,
    VendorOut,
    VendorUpdate,
    VersionIn,
)

router = APIRouter(tags=["procurement"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[Principal, Depends(require("procurement:read"))]
VendorAdmin = Annotated[Principal, Depends(require("vendors:manage"))]
PrMaker = Annotated[Principal, Depends(require("pr:create"))]
PrApprover = Annotated[Principal, Depends(require("pr:approve"))]
Buyer = Annotated[Principal, Depends(require("po:manage"))]
Receiver = Annotated[Principal, Depends(require("grn:create"))]
Version = Annotated[int, Query(ge=1)]


def _csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


# ---------------------------------------------------------------- vendors


@router.get("/vendors", response_model=list[VendorOut], summary="Vendors")
async def list_vendors(
    user: Reader, session: SessionDep, q: Annotated[str | None, Query(max_length=100)] = None
) -> list[VendorOut]:
    counts = await service.open_po_counts(session)
    return [
        views.vendor_out(v, counts.get(v.id, 0))
        for v in await service.list_vendors(session, user, q)
    ]


@router.get("/vendors/{vendor_id}", response_model=VendorOut, summary="One vendor")
async def get_vendor(vendor_id: uuid.UUID, user: Reader, session: SessionDep) -> VendorOut:
    counts = await service.open_po_counts(session)
    return views.vendor_out(
        await service.get_vendor(session, user, vendor_id), counts.get(vendor_id, 0)
    )


@router.post("/vendors", response_model=VendorOut, status_code=201, summary="Create a vendor")
async def create_vendor(data: VendorCreate, user: VendorAdmin, session: SessionDep) -> VendorOut:
    return views.vendor_out(await service.create_vendor(session, user, data))


@router.put("/vendors/{vendor_id}", response_model=VendorOut, summary="Update a vendor")
async def update_vendor(
    vendor_id: uuid.UUID, data: VendorUpdate, user: VendorAdmin, session: SessionDep
) -> VendorOut:
    counts = await service.open_po_counts(session)
    vendor = await service.update_vendor(session, user, vendor_id, data)
    return views.vendor_out(vendor, counts.get(vendor_id, 0))


@router.delete("/vendors/{vendor_id}", status_code=204, summary="Delete a vendor without orders")
async def delete_vendor(
    vendor_id: uuid.UUID, row_version: Version, user: VendorAdmin, session: SessionDep
) -> Response:
    await service.delete_vendor(session, user, vendor_id, row_version)
    return Response(status_code=204)


# ---------------------------------------------------------------- requisitions


@router.get("/requisitions", response_model=list[PrOut], summary="Purchase requisitions")
async def list_prs(
    user: Reader,
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
) -> list[PrOut]:
    prs = await service.list_prs(session, user, project_id=project_id, status=_csv(status))
    return await views.pr_outs(session, prs)


@router.get("/requisitions/{pr_id}", response_model=PrDetail, summary="One requisition")
async def get_pr(pr_id: uuid.UUID, user: Reader, session: SessionDep) -> PrDetail:
    return await views.pr_detail(session, user, await service.get_pr(session, user, pr_id))


@router.post(
    "/projects/{project_id}/requisitions",
    response_model=PrDetail,
    status_code=201,
    summary="Raise a requisition from BOQ shortfall",
)
async def create_pr(
    project_id: uuid.UUID, data: PrFromShortfall, user: PrMaker, session: SessionDep
) -> PrDetail:
    pr = await service.create_pr_from_shortfall(session, user, project_id, data)
    return await views.pr_detail(session, user, pr)


@router.put("/requisitions/{pr_id}", response_model=PrDetail, summary="Edit a draft requisition")
async def update_pr(
    pr_id: uuid.UUID, data: PrUpdate, user: PrMaker, session: SessionDep
) -> PrDetail:
    pr = await service.update_pr(session, user, pr_id, data)
    return await views.pr_detail(session, user, pr)


@router.post("/requisitions/{pr_id}/submit", response_model=PrDetail, summary="Submit for approval")
async def submit_pr(
    pr_id: uuid.UUID, data: VersionIn, user: PrMaker, session: SessionDep
) -> PrDetail:
    pr = await service.submit_pr(session, user, pr_id, data.row_version)
    return await views.pr_detail(session, user, pr)


@router.post("/requisitions/{pr_id}/decision", response_model=PrDetail, summary="Approve or reject")
async def decide_pr(
    pr_id: uuid.UUID, data: PrDecision, user: PrApprover, session: SessionDep
) -> PrDetail:
    pr = await service.decide_pr(
        session, user, pr_id, data.row_version, approve=data.approve, note=data.note
    )
    return await views.pr_detail(session, user, pr)


@router.post(
    "/requisitions/{pr_id}/convert",
    response_model=list[PoRef],
    summary="Create draft purchase orders (one per vendor)",
)
async def convert_pr(
    pr_id: uuid.UUID, data: VersionIn, user: Buyer, session: SessionDep
) -> list[PoRef]:
    orders = await service.convert_pr(session, user, pr_id, data.row_version)
    return [PoRef(id=o.id, number=o.number, status=o.status) for o in orders]


@router.delete("/requisitions/{pr_id}", status_code=204, summary="Delete a draft requisition")
async def delete_pr(
    pr_id: uuid.UUID, row_version: Version, user: PrMaker, session: SessionDep
) -> Response:
    await service.delete_pr(session, user, pr_id, row_version)
    return Response(status_code=204)


# ---------------------------------------------------------------- purchase orders


@router.get("/purchase-orders", response_model=list[PoOut], summary="Purchase orders")
async def list_pos(
    user: Reader,
    session: SessionDep,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
    vendor_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=50)] = None,
) -> list[PoOut]:
    orders = await service.list_pos(
        session,
        user,
        service.PoFilter(status=_csv(status), vendor_id=vendor_id, project_id=project_id, q=q),
    )
    return await views.po_outs(session, orders)


@router.get("/purchase-orders/{po_id}", response_model=PoDetail, summary="One purchase order")
async def get_po(po_id: uuid.UUID, user: Reader, session: SessionDep) -> PoDetail:
    return await views.po_detail(session, user, await service.get_po(session, user, po_id))


@router.post("/purchase-orders", response_model=PoDetail, status_code=201, summary="Create a PO")
async def create_po(data: PoCreate, user: Buyer, session: SessionDep) -> PoDetail:
    return await views.po_detail(session, user, await service.create_po(session, user, data))


@router.put("/purchase-orders/{po_id}", response_model=PoDetail, summary="Edit a draft PO")
async def update_po(po_id: uuid.UUID, data: PoUpdate, user: Buyer, session: SessionDep) -> PoDetail:
    return await views.po_detail(session, user, await service.update_po(session, user, po_id, data))


@router.post("/purchase-orders/{po_id}/issue", response_model=PoDetail, summary="Issue to vendor")
async def issue_po(po_id: uuid.UUID, data: VersionIn, user: Buyer, session: SessionDep) -> PoDetail:
    po = await service.issue_po(session, user, po_id, data.row_version)
    return await views.po_detail(session, user, po)


@router.post("/purchase-orders/{po_id}/cancel", response_model=PoDetail, summary="Cancel a PO")
async def cancel_po(
    po_id: uuid.UUID, data: VersionIn, user: Buyer, session: SessionDep
) -> PoDetail:
    po = await service.cancel_po(session, user, po_id, data.row_version)
    return await views.po_detail(session, user, po)


@router.post("/purchase-orders/{po_id}/close", response_model=PoDetail, summary="Close a PO")
async def close_po(po_id: uuid.UUID, data: NoteIn, user: Buyer, session: SessionDep) -> PoDetail:
    po = await service.close_po(session, user, po_id, data.row_version, data.note)
    return await views.po_detail(session, user, po)


@router.patch("/po-lines/{line_id}", response_model=PoDetail, summary="Update expected date / note")
async def patch_po_line(
    line_id: uuid.UUID, data: PoLinePatch, user: Buyer, session: SessionDep
) -> PoDetail:
    pl = await service.patch_po_line(session, user, line_id, data)
    return await views.po_detail(
        session, user, await service.get_po(session, user, pl.purchase_order_id)
    )


@router.post(
    "/po-lines/{line_id}/cancel", response_model=PoDetail, summary="Cancel a line's remainder"
)
async def cancel_po_line(
    line_id: uuid.UUID, data: VersionIn, user: Buyer, session: SessionDep
) -> PoDetail:
    pl = await service.cancel_po_line(session, user, line_id, data.row_version)
    return await views.po_detail(
        session, user, await service.get_po(session, user, pl.purchase_order_id)
    )


@router.get(
    "/purchase-orders/{po_id}/pdf",
    summary="PO as PDF (company letterhead)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def po_pdf(
    po_id: uuid.UUID, user: Reader, session: SessionDep, settings: SettingsDep
) -> Response:
    number, content = await pdf.po_pdf(session, settings, user, po_id)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{number}.pdf"'},
    )


# ---------------------------------------------------------------- goods receipts


@router.get("/goods-receipts", response_model=list[GrnOut], summary="Goods receipt notes")
async def list_grns(
    user: Reader, session: SessionDep, po_id: uuid.UUID | None = None
) -> list[GrnOut]:
    return await views.grn_outs(session, await service.list_grns(session, user, po_id=po_id))


@router.get("/goods-receipts/{grn_id}", response_model=GrnDetail, summary="One GRN")
async def get_grn(grn_id: uuid.UUID, user: Reader, session: SessionDep) -> GrnDetail:
    return await views.grn_detail(session, user, await service.get_grn(session, user, grn_id))


@router.post("/goods-receipts", response_model=GrnDetail, status_code=201, summary="Receive goods")
async def receive(data: GrnCreate, user: Receiver, session: SessionDep) -> GrnDetail:
    return await views.grn_detail(session, user, await service.receive(session, user, data))


@router.patch("/goods-receipts/{grn_id}", response_model=GrnDetail, summary="Link CoC, edit notes")
async def patch_grn(
    grn_id: uuid.UUID, data: GrnPatch, user: Receiver, session: SessionDep
) -> GrnDetail:
    return await views.grn_detail(
        session, user, await service.patch_grn(session, user, grn_id, data)
    )


@router.post(
    "/grn-lines/{line_id}/resolve-hold",
    response_model=GrnDetail,
    summary="Accept or reject quantity on hold",
)
async def resolve_hold(
    line_id: uuid.UUID, data: HoldResolution, user: Receiver, session: SessionDep
) -> GrnDetail:
    gl = await service.resolve_hold(session, user, line_id, data)
    return await views.grn_detail(
        session, user, await service.get_grn(session, user, gl.goods_receipt_id)
    )


@router.get("/vendor-returns", response_model=list[ReturnOut], summary="Vendor returns")
async def list_returns(
    user: Reader,
    session: SessionDep,
    status: Annotated[str | None, Query(description="Comma-separated statuses")] = None,
) -> list[ReturnOut]:
    return await views.return_outs(
        session, await service.list_returns(session, user, status=_csv(status))
    )


@router.patch("/vendor-returns/{return_id}", response_model=ReturnOut, summary="Update a return")
async def update_return(
    return_id: uuid.UUID, data: ReturnUpdate, user: Receiver, session: SessionDep
) -> ReturnOut:
    ret = await service.update_return(session, user, return_id, data)
    rows = [r for r in await service.list_returns(session, user) if r[0].id == ret.id]
    return (await views.return_outs(session, rows))[0]


# ---------------------------------------------------------------- tracking


@router.get("/projects/{project_id}/tracker", response_model=TrackerOut, summary="Project tracker")
async def project_tracker(project_id: uuid.UUID, user: Reader, session: SessionDep) -> TrackerOut:
    return TrackerOut(**await tracker.project_tracker(session, user, project_id))


@router.get(
    "/procurement/pending",
    response_model=list[PendingLine],
    summary="Open PO lines across projects, by expected date",
)
async def pending(user: Reader, session: SessionDep) -> list[PendingLine]:
    return [PendingLine(**row) for row in await tracker.pending_lines(session, user)]
