"""Production tests build on the procurement arrangement: a project whose module BOQ is
released and (optionally) fully received, so it is clear to build."""

from dataclasses import dataclass
from typing import Any

import pytest

from tests.factories import login, make_user, uniq
from tests.procurement.conftest import Ctx, ctx, po_line

__all__ = ["Plant", "ctx", "plant"]


@dataclass
class Plant:
    ctx: Ctx
    production: dict[str, str]
    parts: list[Any]
    lines: dict[str, dict[str, Any]]
    po: dict[str, Any] | None

    async def wo(
        self, build_qty: int = 5, *, track_serials: bool = True, release: bool = True, **kw: Any
    ) -> dict[str, Any]:
        c = self.ctx
        wo = await c.call(
            "POST",
            "/work-orders",
            expect=201,
            assembly_id=str(c.tree["assembly"].id),
            build_qty=build_qty,
            track_serials=track_serials,
            **kw,
        )
        if release:
            wo = await c.call(
                "POST", f"/work-orders/{wo['id']}/release", row_version=wo["row_version"]
            )
        return wo


async def make_plant(c: Ctx, *, receive: bool = True, build_qty: int = 10) -> Plant:
    """Two parts per board (2 resistors, 1 MCU), BOQ for 10 boards, all received in two lots."""
    res = await c.part(category="Passive")
    mcu = await c.part(category="IC", msl_level=3)
    lines = await c.boq([(res, "2", "Passive"), (mcu, "1", "IC")], build_qty=build_qty)
    po = None
    if receive:
        po = await c.po(
            [
                po_line(
                    res,
                    str(2 * build_qty),
                    allocations=[(lines[res.mpn]["id"], str(2 * build_qty))],
                ),
                po_line(mcu, str(build_qty), allocations=[(lines[mcu.mpn]["id"], str(build_qty))]),
            ]
        )
        half = build_qty
        await c.receive(
            po,
            [
                c.grn_line(po["lines"][0], str(half), batch_lot="RES-L1"),
                c.grn_line(
                    po["lines"][1], str(build_qty), batch_lot="MCU-L1", location_id=c.msl_loc.id
                ),
            ],
        )
        await c.receive(
            po, [c.grn_line(po["lines"][0], str(2 * build_qty - half), batch_lot="RES-L2")]
        )
    name = uniq("prod").replace("-", "_")
    await make_user(c.session, name, roles=("production",))
    return Plant(c, await login(c.client, name), [res, mcu], lines, po)


@pytest.fixture
async def plant(ctx: Ctx) -> Plant:
    return await make_plant(ctx)
