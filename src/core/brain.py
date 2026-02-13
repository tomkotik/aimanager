from __future__ import annotations

from dataclasses import dataclass

import litellm


@dataclass
class BrainResponse:
    content: str
    model: str
    usage: dict
    raw: dict


class Brain:
    """
    AI Brain is a single interface for any LLM provider via LiteLLM.

    Example:
        brain = Brain(provider="openai", model="gpt-4o", temperature=0.3)
        response = await brain.think(system_prompt, messages)
    """

    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float = 0.3,
        api_key: str | None = None,
    ):
        self.provider = provider
        self.model = self._resolve_model(provider, model)
        self.temperature = temperature
        self.api_key = api_key

    async def think(
        self,
        system_prompt: str,
        messages: list[dict],
        temperature: float | None = None,
    ) -> BrainResponse:
        """
        Send a chat completion request.

        Args:
            system_prompt: System prompt (role, knowledge, rules).
            messages: Chat history without the system message.
            temperature: Overrides the default temperature for this call.
        """
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = await litellm.acompletion(
            model=self.model,
            messages=full_messages,
            temperature=temperature if temperature is not None else self.temperature,
            api_key=self.api_key,
        )

        content = response.choices[0].message.content or ""
        usage = self._safe_usage(getattr(response, "usage", None))

        return BrainResponse(
            content=content,
            model=response.model,
            usage=usage,
            raw=response.model_dump(),
        )

    @staticmethod
    def _safe_usage(usage_obj) -> dict:
        """
        Extract a JSON-serializable usage dict from the provider response.

        Some SDKs return nested objects (e.g., token details wrappers) that cannot be stored in JSONB.
        For now we keep only the common integer counters.
        """
        if usage_obj is None:
            return {}

        out: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = None
            if isinstance(usage_obj, dict):
                val = usage_obj.get(key)
            else:
                val = getattr(usage_obj, key, None)

            if isinstance(val, int):
                out[key] = val
        return out

    @staticmethod
    def _resolve_model(provider: str, model: str) -> str:
        """
        LiteLLM uses prefixes for some providers. OpenAI models do not require a prefix.
        """
        prefix_map = {
            "anthropic": "anthropic/",
            "google": "gemini/",
            "openrouter": "openrouter/",
        }
        prefix = prefix_map.get(provider, "")
        if prefix and model.startswith(prefix):
            return model
        return f"{prefix}{model}"

    @classmethod
    def from_config(cls, llm_config, api_key: str | None = None) -> "Brain":
        """Create a Brain instance from an LLMConfig Pydantic model."""
        return cls(
            provider=llm_config.provider,
            model=llm_config.model,
            temperature=llm_config.temperature,
            api_key=api_key,
        )
