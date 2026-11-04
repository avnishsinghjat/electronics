from pathlib import Path

from app.cli import openapi_json

DOC = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.json"


def test_committed_openapi_matches_code() -> None:
    """docs/api/openapi.json is the published API reference; regenerate with `make openapi`."""
    assert DOC.read_text(encoding="utf-8") == openapi_json(), "run `make openapi`"
