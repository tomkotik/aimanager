from src.core.runtime_config import build_runtime_config
from src.core.schemas import ActionConfig, AgentConfig, DialoguePolicyConfig, TenantFullConfig


def test_build_runtime_config_contains_required_fields() -> None:
    cfg = TenantFullConfig(
        agent=AgentConfig.model_validate(
            {
                "id": "a1",
                "name": "Agent",
                "identity": {"role": "r", "persona": "p"},
            }
        ),
        dialogue_policy=DialoguePolicyConfig.model_validate({}),
        actions=[ActionConfig.model_validate({"id": "x", "type": "tool", "trigger": "t"})],
        knowledge={"pricing": "x", "faq": "y"},
    )
    out = build_runtime_config(cfg, tenant_slug="demo")

    assert out["schema_version"] == "1.0.0"
    assert out["tenant_slug"] == "demo"
    assert out["agent"]["id"] == "a1"
    assert out["knowledge_keys"] == ["faq", "pricing"]
