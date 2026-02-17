from __future__ import annotations

"""Agent config schema versioning + migrations.

Goal: keep UI/DB/runtime config compatible across releases.
"""

from copy import deepcopy
from typing import Any

CURRENT_CONFIG_SCHEMA_VERSION = "1.1.0"


def _norm_ver(v: str | None) -> str:
    return (v or "1.0.0").strip() or "1.0.0"


def get_config_schema_descriptor() -> dict[str, Any]:
    return {
        "current_version": CURRENT_CONFIG_SCHEMA_VERSION,
        "supported_versions": ["1.0.0", "1.1.0"],
        "migrations": [
            {
                "from": "1.0.0",
                "to": "1.1.0",
                "notes": [
                    "Добавляет schema_version в корень config",
                    "Добавляет runtime.state_contract и runtime.release_gate defaults",
                ],
            }
        ],
    }


def migrate_agent_config(config: dict[str, Any]) -> dict[str, Any]:
    """Migrate raw config dict to CURRENT_CONFIG_SCHEMA_VERSION."""
    cfg = deepcopy(config or {})
    ver = _norm_ver(cfg.get("schema_version"))

    if ver == "1.0.0":
        cfg = _migrate_1_0_0_to_1_1_0(cfg)
        ver = "1.1.0"

    cfg["schema_version"] = ver
    return cfg


def _migrate_1_0_0_to_1_1_0(cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = deepcopy(cfg)
    runtime = cfg.setdefault("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
        cfg["runtime"] = runtime

    state_contract = runtime.setdefault("state_contract", {})
    if not isinstance(state_contract, dict):
        state_contract = {}
        runtime["state_contract"] = state_contract

    state_contract.setdefault("enabled", True)
    state_contract.setdefault("version", "1.0.0")

    release_gate = runtime.setdefault("release_gate", {})
    if not isinstance(release_gate, dict):
        release_gate = {}
        runtime["release_gate"] = release_gate
    release_gate.setdefault("enabled", True)

    cfg["schema_version"] = "1.1.0"
    return cfg
