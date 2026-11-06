"""Serial number labels: an A4 sheet of 70 x 37 mm labels, each with a QR code of the
serial (generated locally with segno) and the assembly, work order and lot."""

import uuid

import segno
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.pdf import render_pdf
from app.modules.auth.service import Principal
from app.modules.org.models import PcbAssembly
from app.modules.production import service
from app.modules.settings.models import CompanySettings

PER_SHEET = 24


def qr_data_uri(text: str) -> str:
    return str(segno.make(text, error="m").svg_data_uri(scale=4, border=1))


async def labels_pdf(
    session: AsyncSession,
    user: Principal,
    wo_id: uuid.UUID,
    serial_ids: list[uuid.UUID] | None = None,
) -> tuple[str, bytes]:
    wo = await service.get_wo(session, user, wo_id)
    lot = await service.lot_of(session, wo.id)
    units = await service.units_of(session, lot.id) if lot else []
    if serial_ids:
        wanted = set(serial_ids)
        units = [u for u in units if u.id in wanted]
    if not units:
        raise ConflictError("Generate serial numbers first", code="no_serials")
    assembly = await session.get(PcbAssembly, wo.assembly_id)
    company = (await session.execute(select(CompanySettings))).scalar_one_or_none()
    items = [{"serial": u.serial_number, "qr": qr_data_uri(u.serial_number)} for u in units]
    context = {
        "wo_number": wo.number,
        "lot_number": lot.lot_number if lot else "",
        "assembly": f"{assembly.code} rev {assembly.revision} · {assembly.board_name}"
        if assembly
        else "",
        "company": company.company_name if company else "",
        "pages": [items[i : i + PER_SHEET] for i in range(0, len(items), PER_SHEET)],
    }
    return wo.number, await render_pdf("serial_labels.html", context)
