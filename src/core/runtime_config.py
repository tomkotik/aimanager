from __future__ import annotations

from datetime import datetime, timezone

from src.core.schemas import TenantFullConfig

SCHEMA_VERSION = "1.0.0"


def build_runtime_config(cfg: TenantFullConfig, tenant_slug: str) -> dict:
    """Build validated runtime config payload for app/webhooks.

    This payload is intentionally explicit and versioned, so UI/DB/runtime
    stay in sync and can migrate safely in future versions.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_slug": tenant_slug,
        "agent": cfg.agent.model_dump(),
        "dialogue_policy": cfg.dialogue_policy.model_dump(),
        "actions": [a.model_dump() for a in cfg.actions],
        "knowledge_keys": sorted(list(cfg.knowledge.keys())),
    }
