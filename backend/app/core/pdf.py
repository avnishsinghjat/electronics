"""PDF rendering shared by every document: Jinja2 templates in app/templates rendered by
WeasyPrint, fully offline (bundled fonts, images as data URIs, any other URL refused)."""

import asyncio
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))


def _local_fetcher() -> Any:
    """A WeasyPrint URL fetcher that loads bundled template files and data URIs only, so a
    document can never reach the network (air-gapped by design)."""
    from weasyprint.urls import URLFetcher

    class LocalOnlyFetcher(URLFetcher):  # type: ignore[misc]
        def fetch(self, url: str, headers: Any = None) -> Any:
            if url.startswith("data:"):
                return super().fetch(url, headers)
            if url.startswith("file://") and Path(url[7:].split("?")[0]).resolve().is_relative_to(
                TEMPLATES
            ):
                return super().fetch(url, headers)
            raise ValueError(f"Blocked external resource: {url}")

    return LocalOnlyFetcher(fail_on_errors=True)


def render_html(template: str, context: dict[str, Any]) -> str:
    return _env.get_template(template).render(**context)


def _write_pdf(html: str) -> bytes:
    from weasyprint import HTML

    doc = HTML(string=html, base_url=str(TEMPLATES) + "/", url_fetcher=_local_fetcher())
    return doc.write_pdf()  # type: ignore[no-any-return]


async def render_pdf(template: str, context: dict[str, Any]) -> bytes:
    """Render off the event loop (WeasyPrint is CPU-bound)."""
    return await asyncio.to_thread(_write_pdf, render_html(template, context))
