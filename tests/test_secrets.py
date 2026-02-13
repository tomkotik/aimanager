from __future__ import annotations

from src.core.secrets import _slugify, resolve_secret


def test_resolve_secret_from_env(monkeypatch):
    monkeypatch.setenv("AGENTBOX_SECRET_J_ONE_STUDIO_UMNICO_TOKEN", "env-value")
    assert resolve_secret("j-one-studio", "umnico_token") == "env-value"


def test_resolve_secret_from_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    secret_path = tmp_path / "secrets" / "j-one-studio" / "umnico_token"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text("file-value\n", encoding="utf-8")

    assert resolve_secret("j-one-studio", "umnico_token") == "file-value"


def test_resolve_secret_not_found_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_secret("j-one-studio", "missing") is None


def test_slugify_converts_to_env_safe_format():
    assert _slugify("j-one-studio") == "J_ONE_STUDIO"

