"""Purchase order PDF: Jinja2 template + WeasyPrint, fully offline (bundled fonts, logo
embedded as a data URI, every non-local URL refused)."""

import asyncio
import base64
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.service import Principal
from app.modules.parts import service as parts
from app.modules.procurement import service as procurement
from app.modules.procurement.models import PoStatus, PurchaseRequisition
from app.modules.settings import service as company_settings

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))


def _fmt(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{places}f}"


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _local_only(url: str) -> dict[str, Any]:
    """WeasyPrint URL fetcher: bundled files and data URIs only (air-gapped by design)."""
    if url.startswith("file://") and Path(url[7:]).resolve().is_relative_to(TEMPLATES):
        return {"file_obj": Path(url[7:]).open("rb"), "redirected_url": url}
    if url.startswith("data:"):
        from weasyprint.urls import default_url_fetcher

        return default_url_fetcher(url)  # type: ignore[no-any-return]
    raise ValueError(f"Blocked external resource: {url}")


def _render_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html, base_url=str(TEMPLATES) + "/", url_fetcher=_local_only).write_pdf()  # type: ignore[no-any-return]


async def po_context(
    session: AsyncSession, settings: Settings, user: Principal, po_id: uuid.UUID
) -> dict[str, Any]:
    po = await procurement.get_po(session, user, po_id)
    vendor = await procurement.get_vendor(session, user, po.vendor_id)
    lines = await procurement.po_lines(session, po.id)
    part_map = await parts.get_many(session, [pl.part_id for pl in lines])
    company = await company_settings.get_company(session)
    logo_file = await company_settings.get_logo(session)
    logo = None
    if logo_file is not None:
        path = settings.data_dir / logo_file.storage_path
        if path.is_file():
            logo = f"data:{logo_file.mime};base64," + base64.b64encode(path.read_bytes()).decode()
    requisition = (
        await session.get(PurchaseRequisition, po.requisition_id) if po.requisition_id else None
    )
    total = Decimal(0)
    rows = []
    for pl in lines:
        part = part_map[pl.part_id]
        amount = pl.qty_ordered * pl.unit_price if pl.unit_price is not None else None
        if amount is not None and not pl.is_cancelled:
            total += amount
        rows.append(
            {
                "line_no": pl.line_no,
                "mpn": part.mpn,
                "manufacturer": part.manufacturer,
                "description": part.description,
                "qty": _qty(pl.qty_ordered),
                "unit": part.unit,
                "unit_price": _fmt(pl.unit_price, 4 if pl.unit_price and pl.unit_price < 1 else 2),
                "amount": _fmt(amount),
                "expected_date": pl.expected_date.isoformat() if pl.expected_date else None,
                "cancelled": pl.is_cancelled,
            }
        )
    return {
        "po": {
            "number": po.number,
            "order_date": po.order_date.isoformat() if po.order_date else None,
            "currency": po.currency,
            "notes": po.notes,
        },
        "draft": po.status == PoStatus.DRAFT.value,
        "company": {
            "name": company.company_name if company else "",
            "address": company.address if company else None,
            "gstin": company.gstin if company else None,
        },
        "logo": logo,
        "vendor": {
            "code": vendor.code,
            "name": vendor.name,
            "address": vendor.address,
            "city": vendor.city,
            "state": vendor.state,
            "gstin": vendor.gstin,
            "payment_terms": vendor.payment_terms,
            "contacts": vendor.contacts or [],
        },
        "requisition": requisition.number if requisition else None,
        "lines": rows,
        "total": _fmt(total),
    }


async def po_pdf(
    session: AsyncSession, settings: Settings, user: Principal, po_id: uuid.UUID
) -> tuple[str, bytes]:
    context = await po_context(session, settings, user, po_id)
    html = _env.get_template("purchase_order.html").render(**context)
    return context["po"]["number"], await asyncio.to_thread(_render_pdf, html)
