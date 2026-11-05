from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.files import StoredFile, store_file
from app.modules.boq.models import Boq, BoqLine, BoqRevision
from app.modules.org.models import Module, PcbAssembly, Project
from tests.factories import (
    AssemblyFactory,
    BoqFactory,
    BoqLineFactory,
    BoqRevisionFactory,
    DivisionFactory,
    ModuleFactory,
    PartFactory,
    ProjectFactory,
    create,
    login,
    make_user,
)


async def _source(db: AsyncSession, data_dir) -> dict[str, Any]:
    div = await create(db, DivisionFactory)
    project = await create(
        db,
        ProjectFactory,
        division_id=div.id,
        name="Original",
        client_po_ref="PO-1",
        notes="Rush order",
    )
    m1 = await create(
        db, ModuleFactory, project_id=project.id, code="CPU", name="CPU module", qty_to_deliver=25
    )
    m2 = await create(
        db, ModuleFactory, project_id=project.id, code="IO", name="IO module", qty_to_deliver=50
    )
    a1 = await create(
        db,
        AssemblyFactory,
        module_id=m1.id,
        code="CPU1",
        revision="B",
        layer_count=6,
        size_x_mm=Decimal("100.00"),
        finish="ENIG",
    )
    a2 = await create(db, AssemblyFactory, module_id=m2.id, code="DIO", revision="A")
    drawing = await store_file(
        db,
        data_dir,
        b"%PDF-1.7 drawing",
        original_name="cpu-assy.pdf",
        mime="application/pdf",
        ref_type="assembly",
        ref_id=a1.id,
    )
    a1.assembly_drawing_file_id = drawing.id
    deleted = await create(db, ModuleFactory, project_id=project.id, code="OLD")
    deleted.is_deleted = True
    part = await create(db, PartFactory)
    boq = await create(
        db, BoqFactory, project_id=project.id, module_id=m1.id, assembly_id=a1.id, name="CPU BOM"
    )
    rev_a = await create(
        db, BoqRevisionFactory, boq_id=boq.id, revision="A", status="superseded", build_qty=10
    )
    rev_b = await create(
        db, BoqRevisionFactory, boq_id=boq.id, revision="B", status="released", build_qty=25
    )
    await create(
        db, BoqLineFactory, revision_id=rev_a.id, line_key="L1", line_no=1, qty_per_unit=Decimal(1)
    )
    for i, key in enumerate(["L1", "L2"], start=1):
        await create(
            db,
            BoqLineFactory,
            revision_id=rev_b.id,
            line_key=key,
            line_no=i,
            part_id=part.id,
            qty_per_unit=Decimal(i),
            ref_des=f"R{i}",
        )
    await db.flush()
    return {
        "project": project,
        "modules": (m1, m2),
        "assemblies": (a1, a2),
        "drawing": drawing,
        "boq": boq,
    }


async def test_clone_deep_copies_structure_and_boq(
    client: AsyncClient, db_session: AsyncSession, settings
) -> None:
    src = await _source(db_session, settings.data_dir)
    await make_user(db_session, "cloner", roles=("project_manager",))
    h = await login(client, "cloner")
    r = await client.post(
        f"/api/projects/{src['project'].id}/clone",
        headers=h,
        json={
            "name": "Repeat order",
            "client_po_ref": "PO-2",
            "start_date": "2027-01-01",
            "due_date": "2027-03-01",
            "include_boq": True,
        },
    )
    assert r.status_code == 201, r.text
    clone = r.json()
    assert clone["id"] != str(src["project"].id)
    assert clone["code"].startswith("PRJ-") and clone["code"] != src["project"].code
    assert (clone["name"], clone["client_po_ref"], clone["status"]) == (
        "Repeat order",
        "PO-2",
        "draft",
    )
    assert clone["client_name"] == src["project"].client_name
    assert clone["notes"].startswith(f"Cloned from {src['project'].code}.")

    mods = (
        (
            await db_session.execute(
                select(Module).where(Module.project_id == clone["id"]).order_by(Module.code)
            )
        )
        .scalars()
        .all()
    )
    assert [(m.code, m.name, m.qty_to_deliver) for m in mods] == [
        ("CPU", "CPU module", 25),
        ("IO", "IO module", 50),
    ]  # deleted module not copied
    assert not {m.id for m in mods} & {m.id for m in src["modules"]}
    asms = (
        (
            await db_session.execute(
                select(PcbAssembly)
                .where(PcbAssembly.module_id.in_([m.id for m in mods]))
                .order_by(PcbAssembly.code)
            )
        )
        .scalars()
        .all()
    )
    assert [(a.code, a.revision, a.layer_count, a.finish) for a in asms] == [
        ("CPU1", "B", 6, "ENIG"),
        ("DIO", "A", 4, None),
    ]
    cpu = asms[0]
    assert cpu.module_id == mods[0].id
    drawing = await db_session.get(StoredFile, cpu.assembly_drawing_file_id)
    assert drawing is not None and drawing.id != src["drawing"].id
    assert (drawing.ref_type, drawing.ref_id, drawing.sha256) == (
        "assembly",
        cpu.id,
        src["drawing"].sha256,
    )

    boqs = (
        (await db_session.execute(select(Boq).where(Boq.project_id == clone["id"]))).scalars().all()
    )
    assert len(boqs) == 1 and boqs[0].module_id == mods[0].id and boqs[0].assembly_id == cpu.id
    revs = (
        (await db_session.execute(select(BoqRevision).where(BoqRevision.boq_id == boqs[0].id)))
        .scalars()
        .all()
    )
    assert [(r.revision, r.status, r.build_qty) for r in revs] == [
        ("A", "draft", 25)
    ]  # from the released rev B
    lines = (
        (
            await db_session.execute(
                select(BoqLine).where(BoqLine.revision_id == revs[0].id).order_by(BoqLine.line_no)
            )
        )
        .scalars()
        .all()
    )
    assert [(ln.line_key, ln.qty_per_unit, ln.ref_des) for ln in lines] == [
        ("L1", Decimal(1), "R1"),
        ("L2", Decimal(2), "R2"),
    ]

    # Original untouched.
    original = await db_session.get(Project, src["project"].id)
    assert original is not None and original.name == "Original" and original.row_version == 1


async def test_clone_without_boq(client: AsyncClient, db_session: AsyncSession, settings) -> None:
    src = await _source(db_session, settings.data_dir)
    await make_user(db_session, "cloner2", roles=("admin",))
    h = await login(client, "cloner2")
    clone = (
        await client.post(
            f"/api/projects/{src['project'].id}/clone", headers=h, json={"name": "Structure only"}
        )
    ).json()
    assert (
        await db_session.execute(select(Boq).where(Boq.project_id == clone["id"]))
    ).scalars().all() == []
    tree = (await client.get(f"/api/projects/{clone['id']}/tree", headers=h)).json()
    assert tree["project"]["module_count"] == 2
    bad = await client.post(
        f"/api/projects/{src['project'].id}/clone",
        headers=h,
        json={"name": "x", "start_date": "2027-02-01", "due_date": "2027-01-01"},
    )
    assert bad.status_code == 422
