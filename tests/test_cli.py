from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from src.cli import cli


def _write_template(tmp_path: Path) -> None:
    template_dir = tmp_path / "tenants" / "_template"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "agent.yaml").write_text(
        'agent:\n  id: "change-me"\n  name: "My Agent"\n',
        encoding="utf-8",
    )


def test_cli_init_creates_tenant_structure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_template(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["init", "test-tenant"])
    assert result.exit_code == 0

    assert (tmp_path / "tenants" / "test-tenant").is_dir()
    agent_yaml = (tmp_path / "tenants" / "test-tenant" / "agent.yaml").read_text(encoding="utf-8")
    assert 'id: "test-tenant-sales"' in agent_yaml

    assert (tmp_path / "secrets" / "test-tenant").is_dir()
    assert (tmp_path / "secrets" / "test-tenant" / ".gitignore").is_file()


def test_cli_init_existing_tenant_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_template(tmp_path)

    runner = CliRunner()
    ok = runner.invoke(cli, ["init", "test-tenant"])
    assert ok.exit_code == 0

    again = runner.invoke(cli, ["init", "test-tenant"])
    assert again.exit_code != 0
    assert "already exists" in again.output


def test_cli_secrets_set_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["secrets", "set", "test-tenant", "key", "value"])
    assert result.exit_code == 0

    secret_file = tmp_path / "secrets" / "test-tenant" / "key"
    assert secret_file.is_file()
    assert secret_file.read_text(encoding="utf-8") == "value"


def test_cli_secrets_list_shows_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    runner.invoke(cli, ["secrets", "set", "test-tenant", "key", "value"])

    result = runner.invoke(cli, ["secrets", "list", "test-tenant"])
    assert result.exit_code == 0
    assert "key" in result.output


def test_cli_help_shows_usage():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output

