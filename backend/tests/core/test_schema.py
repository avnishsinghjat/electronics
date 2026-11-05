"""Schema-wide rules checked against the real migrated database."""

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.models import BusinessMixin
from app.models import Base

STANDARD = {
    "id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "is_deleted",
    "row_version",
}


async def _db_indexes(engine: AsyncEngine) -> dict[str, list[list[str]]]:
    def load(conn):
        insp = sa_inspect(conn)
        out: dict[str, list[list[str]]] = {}
        for table in insp.get_table_names():
            cols = [ix["column_names"] for ix in insp.get_indexes(table)]
            pk = insp.get_pk_constraint(table)["constrained_columns"]
            out[table] = [*cols, pk]
        return out

    async with engine.connect() as conn:
        return await conn.run_sync(load)


async def test_every_foreign_key_is_indexed(engine: AsyncEngine) -> None:
    indexes = await _db_indexes(engine)
    missing = []
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            col = fk.parent.name
            if not any(ix and ix[0] == col for ix in indexes[table.name]):
                missing.append(f"{table.name}.{col}")
    assert missing == []


async def test_every_status_column_is_indexed(engine: AsyncEngine) -> None:
    indexes = await _db_indexes(engine)
    missing = [
        f"{t.name}.status"
        for t in Base.metadata.sorted_tables
        if "status" in t.c and not any(ix and ix[0] == "status" for ix in indexes[t.name])
    ]
    assert missing == []


def test_business_tables_have_standard_columns() -> None:
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if issubclass(cls, BusinessMixin):
            assert set(mapper.columns.keys()) >= STANDARD, cls.__name__


def test_domain_model_tables_exist() -> None:
    expected = {
        "divisions",
        "projects",
        "modules",
        "pcb_assemblies",
        "build_lots",
        "serial_units",
        "boqs",
        "boq_revisions",
        "boq_lines",
        "parts",
        "part_preferred_vendors",
        "vendors",
        "purchase_requisitions",
        "pr_lines",
        "purchase_orders",
        "po_lines",
        "po_line_allocations",
        "goods_receipts",
        "grn_lines",
        "vendor_returns",
        "inventory_locations",
        "inventory_ledger",
        "stock_balances",
        "stock_reservations",
        "stage_templates",
        "stage_template_steps",
        "work_orders",
        "work_order_stages",
        "stage_progress",
        "qc_templates",
        "qc_template_items",
        "qc_inspections",
        "qc_results",
        "ncrs",
        "qc_reports",
        "document_drafts",
        "design_evaluations",
        "audit_log",
        "files",
        "jobs",
        "document_number_config",
        "document_sequences",
        "users",
        "user_roles",
        "user_scopes",
        "refresh_tokens",
        "company_settings",
    }
    assert expected == set(Base.metadata.tables)
