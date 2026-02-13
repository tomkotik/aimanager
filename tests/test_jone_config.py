from __future__ import annotations

from src.core.config_loader import load_tenant_config
from src.core.prompt_builder import PromptBuilder


def test_load_jone_config_does_not_crash():
    cfg = load_tenant_config("tenants/j-one-studio")
    assert cfg.agent.id


def test_jone_agent_rules_count():
    cfg = load_tenant_config("tenants/j-one-studio")
    assert len(cfg.agent.rules) == 5


def test_jone_intents_count():
    cfg = load_tenant_config("tenants/j-one-studio")
    assert len(cfg.dialogue_policy.intents) == 7


def test_jone_knowledge_files_count():
    cfg = load_tenant_config("tenants/j-one-studio")
    assert len(cfg.knowledge) == 7


def test_prompt_builder_contains_jone_and_prices():
    cfg = load_tenant_config("tenants/j-one-studio")
    prompt = PromptBuilder.build(cfg.agent, cfg.knowledge)
    assert "J-One" in prompt
    assert "4990" in prompt

