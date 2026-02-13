from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.core.schemas import ActionConfig, AgentConfig, DialoguePolicyConfig, TenantFullConfig


def load_tenant_config(tenant_dir: str | Path) -> TenantFullConfig:
    """
    Load a tenant configuration from a directory.

    Expected structure:
      tenant_dir/
        agent.yaml
        dialogue_policy.yaml
        actions.yaml
        knowledge/
          *.md
    """
    tenant_path = Path(tenant_dir)

    agent_path = tenant_path / "agent.yaml"
    if not agent_path.exists():
        raise FileNotFoundError(f"agent.yaml not found in {tenant_path}")

    agent_data = _load_yaml(agent_path)
    agent_config = AgentConfig(**agent_data.get("agent", agent_data))

    dp_path = tenant_path / "dialogue_policy.yaml"
    if dp_path.exists():
        dp_data = _load_yaml(dp_path)
        dialogue_policy = DialoguePolicyConfig(**dp_data.get("dialogue_policy", dp_data))
    else:
        dialogue_policy = DialoguePolicyConfig()

    actions_path = tenant_path / "actions.yaml"
    if actions_path.exists():
        actions_data = _load_yaml(actions_path)
        raw_actions = actions_data.get("actions", actions_data)
        actions = [ActionConfig(**a) for a in (raw_actions if isinstance(raw_actions, list) else [])]
    else:
        actions = []

    knowledge: dict[str, str] = {}
    kb_path = tenant_path / "knowledge"
    if kb_path.is_dir():
        for md_file in sorted(kb_path.glob("*.md")):
            knowledge[md_file.stem] = md_file.read_text(encoding="utf-8")

    return TenantFullConfig(
        agent=agent_config,
        dialogue_policy=dialogue_policy,
        actions=actions,
        knowledge=knowledge,
    )


def list_tenants(tenants_dir: str | Path = "tenants") -> list[str]:
    """Return the list of tenant slugs (directories that contain agent.yaml), excluding _template."""
    base = Path(tenants_dir)
    if not base.exists():
        return []

    return sorted(
        [
            d.name
            for d in base.iterdir()
            if d.is_dir() and (d / "agent.yaml").exists() and d.name != "_template"
        ]
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

