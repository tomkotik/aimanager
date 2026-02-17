from src.core.config_schema import CURRENT_CONFIG_SCHEMA_VERSION, migrate_agent_config


def test_migrate_adds_schema_version_and_runtime_defaults() -> None:
    cfg = {
        "id": "a1",
        "name": "Agent",
        "identity": {"role": "r", "persona": "p"},
    }
    out = migrate_agent_config(cfg)

    assert out["schema_version"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert out["runtime"]["state_contract"]["enabled"] is True
    assert out["runtime"]["release_gate"]["enabled"] is True


def test_migrate_is_idempotent_for_latest() -> None:
    cfg = {
        "id": "a1",
        "name": "Agent",
        "schema_version": CURRENT_CONFIG_SCHEMA_VERSION,
        "identity": {"role": "r", "persona": "p"},
        "runtime": {"state_contract": {"enabled": False}, "release_gate": {"enabled": False}},
    }
    out = migrate_agent_config(cfg)
    assert out["schema_version"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert out["runtime"]["state_contract"]["enabled"] is False
    assert out["runtime"]["release_gate"]["enabled"] is False
