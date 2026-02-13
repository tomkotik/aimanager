"""
Postprocessor — cleans and normalizes LLM output before sending to the user.

Steps:
1. Remove markdown formatting (**, #, [], `)
2. Remove filler phrases ("Понял.", "Хорошо, давайте...", etc.)
3. Enforce sentence and question limits
4. Remove forbidden content based on intent contract
5. Clean up whitespace
"""

from __future__ import annotations

import re

from src.core.schemas import AgentStyle, IntentContract


class Postprocessor:
    """Cleans LLM output to match agent style and intent constraints."""

    # Filler phrases to strip from the beginning of the response (Russian).
    FILLER_PATTERNS = [
        r"^\s*(Понял|Хорошо|Отлично|Ясно|Конечно)[\.\!]?\s*",
        r"^\s*(Давайте уточн|Давайте посчита|Давайте разбер)[^\.\!]*[\.\!]?\s*",
        r"^\s*(Итак|По цене так|Есть несколько)[^\.\!]*[\.\!]?\s*",
    ]

    def __init__(self, style: AgentStyle):
        self.style = style

    # Patterns to strip prepayment mentions.
    PREPAYMENT_PATTERNS = [
        r"[^.!?\n]*(?:50\s*%|предоплат|аванс|оплат(?:а|ить|у)).*?[.!?\n]",
    ]

    def process(
        self,
        text: str,
        intent_id: str | None = None,
        contract: IntentContract | None = None,
        allow_prepayment: bool = False,
    ) -> str:
        """
        Apply all postprocessing steps to the LLM output.

        Args:
            text: Raw LLM response.
            intent_id: Detected intent ID (for context-specific filtering).
            contract: Intent contract (for forbidden word removal).

        Returns:
            Cleaned text ready to send to the user.
        """
        if not text:
            return text

        result = text

        # Step 1: Remove markdown
        if self.style.clean_text:
            result = self._remove_markdown(result)

        # Step 2: Remove filler phrases
        result = self._remove_fillers(result)

        # Step 3: Remove forbidden content (if contract has forbidden words and intent is not the one that needs them)
        if contract and contract.forbidden:
            result = self._remove_forbidden_lines(result, contract.forbidden, intent_id)

        # Step 4: Enforce sentence limit
        result = self._enforce_sentence_limit(result, self.style.max_sentences)

        # Step 5: Enforce question limit
        result = self._enforce_question_limit(result, self.style.max_questions)

        # Step 6: Remove prepayment mentions (unless explicitly allowed).
        if not allow_prepayment:
            result = self._remove_prepayment(result)

        # Step 7: Clean up whitespace
        result = self._clean_whitespace(result)

        return result

    def _remove_prepayment(self, text: str) -> str:
        """Remove sentences mentioning prepayment/advance payment."""
        result = text
        for pattern in self.PREPAYMENT_PATTERNS:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)
        return result

    @staticmethod
    def _remove_markdown(text: str) -> str:
        """Remove markdown formatting: **, __, #, `, []()."""
        t = text
        t = re.sub(r"\*\*", "", t)  # bold
        t = re.sub(r"__", "", t)  # underline
        t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)  # headers
        t = re.sub(r"`", "", t)  # code
        t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)  # [text](url) -> text
        return t

    def _remove_fillers(self, text: str) -> str:
        """Remove common filler/introductory phrases from the start."""
        result = text
        for pattern in self.FILLER_PATTERNS:
            result = re.sub(pattern, "", result, count=1, flags=re.IGNORECASE)
        return result.strip()

    @staticmethod
    def _remove_forbidden_lines(text: str, forbidden: list[str], intent_id: str | None) -> str:
        """Remove lines that contain forbidden words."""
        lines = text.split("\n")
        filtered: list[str] = []
        for line in lines:
            line_lower = line.lower()
            has_forbidden = any(word.lower() in line_lower for word in forbidden)
            if not has_forbidden:
                filtered.append(line)
        return "\n".join(filtered)

    @staticmethod
    def _enforce_sentence_limit(text: str, max_sentences: int) -> str:
        """Trim text to max_sentences."""
        # Split by sentence-ending punctuation, keeping the delimiter.
        parts = re.split(r"([.!?]+)", text)
        sentences_found = 0
        result_parts: list[str] = []

        for i in range(0, len(parts), 2):
            sentence = parts[i].strip()
            if not sentence:
                continue
            sentences_found += 1
            if sentences_found > max_sentences:
                break
            result_parts.append(parts[i])
            # Add the delimiter if available.
            if i + 1 < len(parts):
                result_parts.append(parts[i + 1])

        return "".join(result_parts).strip()

    @staticmethod
    def _enforce_question_limit(text: str, max_questions: int) -> str:
        """If text has too many question marks, truncate after the Nth one."""
        count = 0
        for i, ch in enumerate(text):
            if ch == "?":
                count += 1
                if count >= max_questions:
                    # Keep up to and including this question mark.
                    return text[: i + 1].strip()
        return text

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        """Normalize whitespace: collapse multiple newlines, trim."""
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()
