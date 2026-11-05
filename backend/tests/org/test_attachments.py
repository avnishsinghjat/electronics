import io

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from tests.factories import DivisionFactory, ProjectFactory, create, login, make_user, project_tree

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
HTML = b"<html><script>alert(1)</script></html>"


async def _upload(
    client: AsyncClient,
    h: dict[str, str],
    ref_type: str,
    ref_id: object,
    name: str,
    content: bytes,
    mime: str,
):
    return await client.post(
        "/api/files",
        headers=h,
        data={"ref_type": ref_type, "ref_id": str(ref_id)},
        files={"file": (name, io.BytesIO(content), mime)},
    )


async def test_upload_list_download_preview_delete(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tree = await project_tree(db_session)
    await make_user(db_session, "att_pm", roles=("project_manager",))
    h = await login(client, "att_pm")
    pdf = await _upload(
        client, h, "project", tree["project"].id, "spec.pdf", PDF, "application/octet-stream"
    )
    assert pdf.status_code == 201, pdf.text
    body = pdf.json()
    assert (body["mime"], body["previewable"], body["uploaded_by_name"]) == (
        "application/pdf",
        True,
        "Test User",
    )
    disguised = await _upload(
        client, h, "project", tree["project"].id, "notes.html", HTML, "image/png"
    )
    assert disguised.json()["mime"] == "application/octet-stream"  # declared type is not trusted
    assert disguised.json()["previewable"] is False

    listed = (
        await client.get(f"/api/files?ref_type=project&ref_id={tree['project'].id}", headers=h)
    ).json()
    assert [f["original_name"] for f in listed] == ["notes.html", "spec.pdf"]

    inline = await client.get(f"/api/files/{body['id']}/content?disposition=inline", headers=h)
    assert inline.status_code == 200 and inline.content == PDF
    assert inline.headers["content-type"] == "application/pdf"
    assert inline.headers["content-disposition"].startswith("inline;")
    assert "sandbox" in inline.headers["content-security-policy"]
    forced = await client.get(
        f"/api/files/{disguised.json()['id']}/content?disposition=inline", headers=h
    )
    assert forced.headers["content-disposition"].startswith("attachment;")
    assert forced.headers["content-type"] == "application/octet-stream"

    gone = await client.delete(f"/api/files/{body['id']}?row_version=1", headers=h)
    assert gone.status_code == 204
    assert (await client.get(f"/api/files/{body['id']}", headers=h)).status_code == 404
    assert [
        f["original_name"]
        for f in (
            await client.get(f"/api/files?ref_type=project&ref_id={tree['project'].id}", headers=h)
        ).json()
    ] == ["notes.html"]
    audit = (
        (
            await db_session.execute(
                select(AuditLog.action)
                .where(AuditLog.entity_id == body["id"])
                .order_by(AuditLog.id)
            )
        )
        .scalars()
        .all()
    )
    assert audit == ["insert", "soft_delete"]


async def test_assembly_drawing_link_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    tree = await project_tree(db_session)
    await make_user(db_session, "att_admin")
    h = await login(client, "att_admin")
    other = await _upload(client, h, "project", tree["project"].id, "x.pdf", PDF, "application/pdf")
    a_id = tree["assembly"].id
    bad = await client.patch(
        f"/api/assemblies/{a_id}",
        headers=h,
        json={"row_version": 1, "assembly_drawing_file_id": other.json()["id"]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_reference"
    drawing = await _upload(client, h, "assembly", a_id, "assy.png", PNG, "image/png")
    ok = await client.patch(
        f"/api/assemblies/{a_id}",
        headers=h,
        json={"row_version": 1, "assembly_drawing_file_id": drawing.json()["id"]},
    )
    assert ok.status_code == 200
    in_use = await client.delete(f"/api/files/{drawing.json()['id']}?row_version=1", headers=h)
    assert in_use.status_code == 409 and in_use.json()["error"]["code"] == "file_in_use"


async def test_attachment_permissions_scope_and_limits(
    client: AsyncClient, db_session: AsyncSession, settings
) -> None:
    div_a = await create(db_session, DivisionFactory)
    div_b = await create(db_session, DivisionFactory)
    pa = await create(db_session, ProjectFactory, division_id=div_a.id)
    pb = await create(db_session, ProjectFactory, division_id=div_b.id)
    await make_user(db_session, "att_admin2")
    admin = await login(client, "att_admin2")
    secret = await _upload(client, admin, "project", pb.id, "b.pdf", PDF, "application/pdf")

    await make_user(
        db_session, "att_scoped", roles=("project_manager",), scopes=(("project", pa.id),)
    )
    scoped = await login(client, "att_scoped")
    assert (
        await _upload(client, scoped, "project", pb.id, "x.pdf", PDF, "application/pdf")
    ).status_code == 404
    assert (
        await client.get(f"/api/files/{secret.json()['id']}/content", headers=scoped)
    ).status_code == 404
    assert (
        await client.get(f"/api/files?ref_type=project&ref_id={pb.id}", headers=scoped)
    ).status_code == 404

    await make_user(db_session, "att_viewer", roles=("viewer",))
    viewer = await login(client, "att_viewer")
    assert (
        await _upload(client, viewer, "project", pa.id, "x.pdf", PDF, "application/pdf")
    ).status_code == 403
    assert (
        await client.delete(f"/api/files/{secret.json()['id']}?row_version=1", headers=viewer)
    ).status_code == 403

    bad_type = await _upload(client, admin, "spaceship", pa.id, "x.pdf", PDF, "application/pdf")
    assert bad_type.status_code == 422 and bad_type.json()["error"]["code"] == "invalid_ref_type"
    missing = await _upload(
        client,
        admin,
        "project",
        "00000000-0000-0000-0000-000000000001",
        "x.pdf",
        PDF,
        "application/pdf",
    )
    assert missing.status_code == 404
    settings.max_upload_mb = 1
    too_big = await _upload(
        client,
        admin,
        "project",
        pa.id,
        "big.bin",
        b"0" * (1024 * 1024 + 10),
        "application/octet-stream",
    )
    assert too_big.status_code == 413
    empty = await _upload(client, admin, "project", pa.id, "empty.txt", b"", "text/plain")
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "empty_file"
