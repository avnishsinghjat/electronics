"""Background jobs for the BOQ import wizard.

boq.parse     read the uploaded file, detect encoding/delimiter/header, suggest a mapping
              (from a matching saved template if there is one)
boq.validate  apply the mapping, validate and merge; store the result for preview
"""

import uuid
from typing import Any

from app.core.files import StoredFile
from app.core.jobs import JobContext, job_handler
from app.modules.boq import importer
from app.modules.boq.models import Boq, BoqImport, BoqMappingTemplate, ImportStatus
from app.modules.org.models import Project
from app.modules.parts import service as parts

PREVIEW_ROWS = 25


async def _load(ctx: JobContext) -> BoqImport:
    imp = await ctx.session.get(
        BoqImport, uuid.UUID(ctx.payload["import_id"]), with_for_update=True
    )
    if imp is None:
        raise LookupError("import not found")
    return imp


@job_handler("boq.parse")
async def parse(ctx: JobContext) -> dict[str, Any]:
    imp = await _load(ctx)
    record = await ctx.session.get(StoredFile, imp.file_id)
    assert record is not None
    content = (ctx.settings.data_dir / record.storage_path).read_bytes()
    try:
        table = importer.read_table(content, record.original_name)
    except importer.ImportFormatError as exc:
        imp.status = ImportStatus.FAILED.value
        imp.error = str(exc)
        return {"status": "failed", "error": str(exc)}
    header = importer.detect_header(table.rows)
    headers = table.rows[header] if table.rows else []
    mapping = importer.suggest_mapping(headers)
    boq = await ctx.session.get(Boq, imp.boq_id)
    project = await ctx.session.get(Project, boq.project_id) if boq else None
    from app.modules.boq.service import _matching_template  # shared with the API

    template_id = await _matching_template(
        ctx.session, headers, project.client_name if project else None
    )
    if template_id:
        template = await ctx.session.get(BoqMappingTemplate, template_id)
        if template is not None:
            mapping = importer.mapping_from_template(headers, template.mapping) or mapping
            imp.template_id = template.id
    imp.encoding, imp.delimiter, imp.sheet = table.encoding, table.delimiter, table.sheet
    imp.header_row, imp.headers, imp.rows, imp.mapping = header, headers, table.rows, mapping
    imp.status = ImportStatus.PARSED.value
    imp.error = None
    return {"rows": len(table.rows), "header_row": header, "mapped": sorted(mapping)}


@job_handler("boq.validate")
async def validate(ctx: JobContext) -> dict[str, Any]:
    imp = await _load(ctx)
    rows = imp.rows or []
    mpns = []
    mpn_col = (imp.mapping or {}).get("mpn")
    if mpn_col is not None:
        mpns = [
            r[mpn_col] for r in rows[(imp.header_row or 0) + 1 :] if mpn_col < len(r) and r[mpn_col]
        ]
    master = await parts.by_normalised_mpn(ctx.session, mpns)
    known = {key: (p.mpn, p.manufacturer) for key, p in master.items()}
    result = importer.validate(
        rows,
        imp.header_row or 0,
        imp.mapping or {},
        known,
        decimal_comma=bool(ctx.payload.get("decimal_comma")),
    )
    imp.result = result.to_json()
    imp.status = ImportStatus.VALIDATED.value
    return dict(result.stats)
