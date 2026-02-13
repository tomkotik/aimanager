from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.brain import BrainResponse
from src.core.config_loader import load_tenant_config
from src.core.pipeline import IncomingMessage, MessagePipeline, PipelineContext


def _ctx(message_text: str) -> PipelineContext:
    cfg = load_tenant_config("tenants/j-one-studio")
    incoming = IncomingMessage(
        channel_type="umnico",
        channel_conversation_id="conv-1",
        channel_message_id="msg-1",
        text=message_text,
        metadata={},
    )
    return PipelineContext(
        incoming=incoming,
        agent_config=cfg.agent,
        knowledge=cfg.knowledge,
        dialogue_policy=cfg.dialogue_policy,
    )


@pytest.mark.asyncio
async def test_pricing_detected_and_markdown_removed():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(content="**Стоимость 4990₽**", model="gpt-4o", usage={}, raw={})
    )
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Сколько стоит?"))
    assert out.detected_intent == "PRICING"
    assert out.outgoing is not None
    assert out.outgoing.text == "Стоимость 4990₽"


@pytest.mark.asyncio
async def test_address_detected():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(
            content="Адрес: Нижняя Сыромятническая 11кБ, 9 этаж.",
            model="gpt-4o",
            usage={},
            raw={},
        )
    )
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Где вы?"))
    assert out.detected_intent == "ADDRESS"


@pytest.mark.asyncio
async def test_greeting_detected():
    brain = AsyncMock()
    brain.think = AsyncMock(return_value=BrainResponse(content="Здравствуйте!)", model="gpt-4o", usage={}, raw={}))
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Привет!"))
    assert out.detected_intent == "GREETING"


@pytest.mark.asyncio
async def test_brain_markdown_removed():
    brain = AsyncMock()
    brain.think = AsyncMock(return_value=BrainResponse(content="**жирный**", model="gpt-4o", usage={}, raw={}))
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Привет!"))
    assert out.outgoing is not None
    assert out.outgoing.text == "жирный"


@pytest.mark.asyncio
async def test_filler_removed():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(content="Понял. Стоимость 4990₽", model="gpt-4o", usage={}, raw={})
    )
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Сколько стоит?"))
    assert out.outgoing is not None
    assert out.outgoing.text == "Стоимость 4990₽"


@pytest.mark.asyncio
async def test_sentence_limit_enforced():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(content="One. Two. Three. Four. Five.", model="gpt-4o", usage={}, raw={})
    )
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Привет!"))
    assert out.outgoing is not None
    assert out.outgoing.text == "One. Two. Three."


@pytest.mark.asyncio
async def test_brain_error_sets_ctx_error_and_outgoing_none():
    brain = AsyncMock()
    brain.think = AsyncMock(side_effect=RuntimeError("LLM error"))
    pipeline = MessagePipeline(brain=brain)

    out = await pipeline.process(_ctx("Сколько стоит?"))
    assert out.error is not None
    assert out.outgoing is None

