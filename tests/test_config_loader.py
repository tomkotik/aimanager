from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config_loader import list_tenants, load_tenant_config


def test_load_template_config_does_not_crash():
    cfg = load_tenant_config("tenants/_template")
    assert cfg.agent.id
    assert cfg.agent.name


def test_invalid_yaml_raises(tmp_path: Path):
    tenant_dir = tmp_path / "bad"
    tenant_dir.mkdir()
    (tenant_dir / "agent.yaml").write_text("agent: [", encoding="utf-8")

    with pytest.raises(Exception):
        load_tenant_config(tenant_dir)


def test_knowledge_files_are_loaded(tmp_path: Path):
    tenant_dir = tmp_path / "t1"
    (tenant_dir / "knowledge").mkdir(parents=True)
    (tenant_dir / "agent.yaml").write_text(
        """
agent:
  id: "t1"
  name: "Test"
  identity:
    role: "role"
    persona: "persona"
""".lstrip(),
        encoding="utf-8",
    )
    (tenant_dir / "knowledge" / "pricing.md").write_text("# Цены\n4990", encoding="utf-8")

    cfg = load_tenant_config(tenant_dir)
    assert "pricing" in cfg.knowledge
    assert "4990" in cfg.knowledge["pricing"]


def test_list_tenants_excludes_template(tmp_path: Path):
    tenants_dir = tmp_path / "tenants"
    (tenants_dir / "_template").mkdir(parents=True)
    (tenants_dir / "_template" / "agent.yaml").write_text("agent: {}", encoding="utf-8")
    (tenants_dir / "a").mkdir()
    (tenants_dir / "a" / "agent.yaml").write_text("agent: {}", encoding="utf-8")
    (tenants_dir / "b").mkdir()

    slugs = list_tenants(tenants_dir)
    assert slugs == ["a"]


def test_missing_agent_yaml_raises(tmp_path: Path):
    tenant_dir = tmp_path / "missing"
    tenant_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        load_tenant_config(tenant_dir)

