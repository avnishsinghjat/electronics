"""The shared PDF renderer: bundled fonts and data-URI images load; anything else is
refused, so documents can never reach the network."""

import pytest

from app.core.pdf import _write_pdf, render_pdf

PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def test_bundled_fonts_and_data_images_render() -> None:
    html = (
        '<style>@font-face{font-family:I;src:url("fonts/inter-latin-wght-normal.woff2")}'
        "body{font-family:I}</style>"
        f'<img src="{PIXEL}">Serial FT-CPU1-2026-00001'
    )
    pdf = _write_pdf(html)
    assert pdf.startswith(b"%PDF") and b"/Image" in pdf


@pytest.mark.parametrize(
    "url", ["http://example.com/logo.png", "https://cdn.example.com/a.css", "file:///etc/hostname"]
)
def test_external_and_local_files_outside_templates_are_blocked(url: str) -> None:
    with pytest.raises(BaseException, match="fetching"):
        _write_pdf(f'<img src="{url}">')


async def test_render_pdf_runs_a_template() -> None:
    pdf = await render_pdf(
        "serial_labels.html",
        {
            "wo_number": "WO-1",
            "lot_number": "LOT-1",
            "assembly": "CPU1",
            "company": "Acme",
            "pages": [[{"serial": "SN-1", "qr": PIXEL}]],
        },
    )
    assert pdf.startswith(b"%PDF")
