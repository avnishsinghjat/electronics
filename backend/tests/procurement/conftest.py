"""Shared arrangement for procurement tests: a project with a released BOQ whose lines are
linked to parts, a vendor, and one user per role, all through the real API."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import InventoryLocation
from app.modules.settings.models import CompanySettings
from app.seed import seed_reference_data
from tests.factories import (
    ModuleFactory,
    PartFactory,
    VendorFactory,
    create,
    login,
    make_user,
    project_tree,
    uniq,
)


@dataclass
class Ctx:
    client: AsyncClient
    session: AsyncSession
    tree: dict[str, Any]
    pm: dict[str, str]
    buyer: dict[str, str]
    stores: dict[str, str]
    qc_lead: dict[str, str]
    viewer: dict[str, str]
    vendor: Any
    stores_loc: Any
    msl_loc: Any

    async def get(self, path: str, h: dict[str, str] | None = None, **params: Any) -> Any:
        r = await self.client.get(f"/api{path}", headers=h or self.pm, params=params)
        assert r.status_code == 200, r.text
        return r.json()

    async def call(
        self,
        method: str,
        path: str,
        h: dict[str, str] | None = None,
        expect: int = 200,
        **body: Any,
    ) -> Any:
        r = await self.client.request(method, f"/api{path}", headers=h or self.pm, json=body)
        assert r.status_code == expect, r.text
        return r.json() if r.content else None

    async def part(self, mpn: str | None = None, **kw: Any) -> Any:
        return await create(self.session, PartFactory, mpn=mpn or uniq("MPN").upper(), **kw)

    async def boq(
        self,
        lines: list[tuple[Any, ...]],
        *,
        build_qty: int = 10,
        module_id: Any = None,
        project_id: Any = None,
        release: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """lines: (part, qty_per_unit, category[, extra]) -> {mpn: tracked BOQ line}."""
        project = project_id or self.tree["project"].id
        b = await self.call(
            "POST",
            f"/projects/{project}/boqs",
            expect=201,
            name=uniq("BOM"),
            module_id=str(module_id or self.tree["module"].id),
            build_qty=build_qty,
        )
        rev = b["revisions"][0]
        payload = []
        for spec in lines:
            part, qty, category = spec[0], spec[1], spec[2]
            extra = spec[3] if len(spec) > 3 else {}
            payload.append(
                {
                    "line_key": None,
                    "part_id": str(part.id),
                    "ref_des": None,
                    "qty_per_unit": qty,
                    "mpn": part.mpn,
                    "manufacturer": part.manufacturer,
                    "description": part.description,
                    "value": None,
                    "package": None,
                    "category": category,
                    "unit": "pcs",
                    "dnp": False,
                    "attrition_pct": "0",
                    "unit_price": None,
                    "notes": None,
                    **extra,
                }
            )
        saved = await self.call(
            "PUT",
            f"/boq-revisions/{rev['id']}/lines",
            row_version=rev["row_version"],
            lines=payload,
        )
        if release:
            await self.call(
                "POST", f"/boq-revisions/{rev['id']}/release", row_version=saved["row_version"]
            )
        detail = await self.get(f"/boq-revisions/{rev['id']}")
        return {ln["mpn"]: ln for ln in detail["lines"]}

    async def tracker(self, project_id: Any = None) -> dict[str, Any]:
        return await self.get(f"/projects/{project_id or self.tree['project'].id}/tracker")

    async def line(self, mpn: str, project_id: Any = None) -> dict[str, Any]:
        t = await self.tracker(project_id)
        return next(ln for ln in t["lines"] if ln["mpn"] == mpn)

    async def po(
        self,
        lines: list[dict[str, Any]],
        *,
        issue: bool = True,
        vendor_id: Any = None,
    ) -> dict[str, Any]:
        po = await self.call(
            "POST",
            "/purchase-orders",
            h=self.buyer,
            expect=201,
            vendor_id=str(vendor_id or self.vendor.id),
            lines=lines,
        )
        if issue:
            po = await self.call(
                "POST",
                f"/purchase-orders/{po['id']}/issue",
                h=self.buyer,
                row_version=po["row_version"],
            )
        return po

    async def receive(
        self, po: dict[str, Any], lines: list[dict[str, Any]], expect: int = 201
    ) -> Any:
        return await self.call(
            "POST",
            "/goods-receipts",
            h=self.stores,
            expect=expect,
            purchase_order_id=po["id"],
            delivery_note_ref="DN-1",
            lines=lines,
        )

    def grn_line(self, po_line: dict[str, Any], accepted: str, **kw: Any) -> dict[str, Any]:
        rejected = Decimal(kw.pop("rejected", "0"))
        hold = Decimal(kw.pop("hold", "0"))
        acc = Decimal(accepted)
        return {
            "po_line_id": po_line["id"],
            "location_id": str(kw.pop("location_id", self.stores_loc.id)),
            "qty_received": str(acc + rejected + hold),
            "qty_accepted": str(acc),
            "qty_rejected": str(rejected),
            "qty_on_hold": str(hold),
            "reject_reason": "Damaged reel" if rejected else None,
            **kw,
        }


def po_line(
    part: Any, qty: str, price: str | None = "1.50", allocations: Any = (), **kw: Any
) -> dict[str, Any]:
    return {
        "part_id": str(part.id),
        "qty_ordered": qty,
        "unit_price": price,
        "expected_date": kw.pop("expected_date", None),
        "allocations": [{"boq_line_id": a[0], "qty": a[1]} for a in allocations],
        **kw,
    }


@pytest.fixture
async def ctx(client: AsyncClient, db_session: AsyncSession) -> Ctx:
    await seed_reference_data(db_session)
    if (await db_session.execute(select(CompanySettings))).scalar_one_or_none() is None:
        db_session.add(CompanySettings(company_name="Test Electronics", address="Plot 4, MIDC"))
    tree = await project_tree(db_session)
    vendor = await create(db_session, VendorFactory, lead_time_days=14)
    users = {}
    for role in ("project_manager", "purchase", "stores", "qc_lead", "viewer"):
        name = uniq(role).replace("-", "_")
        await make_user(db_session, name, roles=(role,))
        users[role] = await login(client, name)
    locs = {
        loc.code: loc for loc in (await db_session.execute(select(InventoryLocation))).scalars()
    }
    return Ctx(
        client=client,
        session=db_session,
        tree=tree,
        pm=users["project_manager"],
        buyer=users["purchase"],
        stores=users["stores"],
        qc_lead=users["qc_lead"],
        viewer=users["viewer"],
        vendor=vendor,
        stores_loc=locs["STORES"],
        msl_loc=locs["MSL-DRY-1"],
    )


__all__ = ["Ctx", "ModuleFactory", "po_line"]
