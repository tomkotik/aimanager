from __future__ import annotations

from src.core.schemas import AgentConfig


class PromptBuilder:
    """Builds a system prompt from an agent config and a knowledge base."""

    @staticmethod
    def build(agent_config: AgentConfig, knowledge: dict[str, str], extra_context: str = "") -> str:
        sections: list[str] = []

        sections.append(f"## ROLE\n{agent_config.identity.role}")
        sections.append(f"## PERSONA\n{agent_config.identity.persona}")
        if agent_config.identity.fallback_phrase:
            sections.append(
                f'If asked who you are, say: "{agent_config.identity.fallback_phrase}"'
            )

        style = agent_config.style
        style_lines = [
            f"- Tone: {style.tone}",
            f"- Politeness: {style.politeness}",
            f"- Emoji: {style.emoji_policy}",
            f"- Max sentences per reply: {style.max_sentences}",
            f"- Max questions per reply: {style.max_questions}",
        ]
        if style.clean_text:
            style_lines.append("- NO markdown. No **bold**, # headers, [links]. Plain text only.")
        sections.append("## STYLE\n" + "\n".join(style_lines))

        if agent_config.rules:
            rules_text: list[str] = []
            for i, rule in enumerate(agent_config.rules, 1):
                rule_line = f"{i}. [{rule.priority.upper()}] {rule.description}"
                if rule.positive_example:
                    rule_line += f"\n   ✓ Correct: {rule.positive_example}"
                if rule.negative_example:
                    rule_line += f"\n   ✗ Wrong: {rule.negative_example}"
                rules_text.append(rule_line)
            sections.append("## CRITICAL RULES\n" + "\n".join(rules_text))

        if knowledge:
            kb_text = "\n\n".join(
                [f"### {name.upper().replace('_', ' ')}\n{content}" for name, content in knowledge.items()]
            )
            sections.append(f"## KNOWLEDGE BASE\n{kb_text}")

        if extra_context:
            sections.append(f"## CURRENT CONTEXT\n{extra_context}")

        sections.append(
            "## OUTPUT RULES\n"
            "1. Reply in the same language as the user.\n"
            "2. If the user mentions a relative date ('tomorrow', 'next Tuesday'), "
            "always reply with an explicit date (DD.MM.YYYY) and time (HH:MM).\n"
            "3. Follow all CRITICAL RULES above. Violations are forbidden."
        )

        return "\n\n".join(sections)

