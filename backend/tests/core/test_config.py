import pytest

from app.core.config import Settings


def test_air_gapped_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FABTRACK_AIR_GAPPED", raising=False)
    assert Settings(_env_file=None).air_gapped is True


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABTRACK_AIR_GAPPED", "false")
    monkeypatch.setenv("FABTRACK_DATA_DIR", "/srv/fabtrack")
    s = Settings(_env_file=None)
    assert s.air_gapped is False
    assert str(s.data_dir) == "/srv/fabtrack"


def test_invalid_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FABTRACK_ENV", "staging")
    with pytest.raises(ValueError, match="env"):
        Settings(_env_file=None)
