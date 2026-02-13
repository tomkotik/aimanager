from __future__ import annotations

from src.core.brain import Brain
from src.core.prompt_builder import PromptBuilder
from src.core.schemas import AgentConfig, AgentIdentity, AgentRule, LLMConfig


def test_resolve_model_openai():
    assert Brain._resolve_model("openai", "gpt-4o") == "gpt-4o"


def test_resolve_model_anthropic():
    assert (
        Brain._resolve_model("anthropic", "claude-sonnet-4-20250514")
        == "anthropic/claude-sonnet-4-20250514"
    )


def test_resolve_model_google():
    assert Brain._resolve_model("google", "gemini-pro") == "gemini/gemini-pro"


def test_from_config():
    llm = LLMConfig(provider="openai", model="gpt-4o", temperature=0.7, max_history=10)
    brain = Brain.from_config(llm)
    assert brain.provider == "openai"
    assert brain.model == "gpt-4o"
    assert brain.temperature == 0.7


def test_safe_usage_extracts_only_int_counters():
    class _Usage:
        prompt_tokens = 1
        completion_tokens = 2
        total_tokens = 3
        prompt_tokens_details = object()

    assert Brain._safe_usage(_Usage()) == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


def test_prompt_builder_includes_sections():
    agent = AgentConfig(
        id="a1",
        name="Agent",
        identity=AgentIdentity(role="Support", persona="Helpful"),
        rules=[
            AgentRule(id="r1", priority="critical", description="Rule 1"),
        ],
        llm=LLMConfig(),
    )
    prompt = PromptBuilder.build(agent_config=agent, knowledge={"pricing": "4990"}, extra_context="")
    assert "## ROLE" in prompt
    assert "## STYLE" in prompt
    assert "## CRITICAL RULES" in prompt
    assert "## KNOWLEDGE BASE" in prompt


def test_prompt_builder_without_knowledge_has_no_kb_section():
    agent = AgentConfig(
        id="a1",
        name="Agent",
        identity=AgentIdentity(role="Support", persona="Helpful"),
        rules=[],
        llm=LLMConfig(),
    )
    prompt = PromptBuilder.build(agent_config=agent, knowledge={}, extra_context="")
    assert "## KNOWLEDGE BASE" not in prompt


def test_prompt_builder_with_extra_context_has_context_section():
    agent = AgentConfig(
        id="a1",
        name="Agent",
        identity=AgentIdentity(role="Support", persona="Helpful"),
        rules=[],
        llm=LLMConfig(),
    )
    prompt = PromptBuilder.build(
        agent_config=agent, knowledge={}, extra_context="Calendar: free slots"
    )
    assert "## CURRENT CONTEXT" in prompt
