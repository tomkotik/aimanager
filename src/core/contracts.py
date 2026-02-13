"""
Contract Validator — checks that LLM output complies with intent and style constraints.

Usage:
    validator = ContractValidator(style)
    result = validator.validate(text, contract)
    if not result.ok:
        print(result.violations)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.schemas import AgentStyle, IntentContract


@dataclass
class ValidationResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


class ContractValidator:
    """
    Validates LLM output against:
    1. Intent contract (must_include_any, forbidden words)
    2. Style limits (max_sentences, max_questions)
    """

    def __init__(self, style: AgentStyle):
        self.max_sentences = style.max_sentences
        self.max_questions = style.max_questions

    def validate(self, text: str, contract: IntentContract | None = None) -> ValidationResult:
        """
        Validate the response text.

        Args:
            text: LLM response text.
            contract: Intent-specific contract (optional).

        Returns:
            ValidationResult with ok=True/False and list of violations.
        """
        violations: list[str] = []

        # 1. Check sentence count
        sentences = self._count_sentences(text)
        if sentences > self.max_sentences:
            violations.append(f"max_sentences: {sentences} > {self.max_sentences}")

        # 2. Check question count
        questions = text.count("?")
        if questions > self.max_questions:
            violations.append(f"max_questions: {questions} > {self.max_questions}")

        # 3. Check contract constraints
        if contract:
            # must_include_any: at least one of the words must be present
            if contract.must_include_any:
                found = any(word in text for word in contract.must_include_any)
                if not found:
                    violations.append(f"must_include: none of {contract.must_include_any} found")

            # forbidden: none of the words should be present
            for word in contract.forbidden:
                if word.lower() in text.lower():
                    violations.append(f"forbidden: '{word}' found")

        return ValidationResult(ok=len(violations) == 0, violations=violations)

    @staticmethod
    def _count_sentences(text: str) -> int:
        """Count sentences by splitting on sentence-ending punctuation."""
        import re

        parts = re.split(r"[.!?]+", text)
        return len([p for p in parts if p.strip()])

