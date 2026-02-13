from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.core.brain import BrainResponse
from src.core.pipeline import IncomingMessage, MessagePipeline, PipelineContext
from src.core.schemas import AgentConfig, AgentIdentity, DialoguePolicyConfig, LLMConfig


def _make_agent_config() -> AgentConfig:
    return AgentConfig(
        id="a1",
        name="Agent",
        identity=AgentIdentity(role="Support", persona="Helpful"),
        llm=LLMConfig(max_history=5),
    )


def test_pipeline_context_minimal():
    incoming = IncomingMessage(
        channel_type="telegram",
        channel_conversation_id="c1",
        channel_message_id="m1",
        text="hi",
    )
    ctx = PipelineContext(
        incoming=incoming,
        agent_config=_make_agent_config(),
        knowledge={},
        dialogue_policy=DialoguePolicyConfig(),
    )
    assert ctx.history == []
    assert ctx.detected_intent is None
    assert ctx.error is None


def test_incoming_message_from_dict_like():
    payload = {
        "channel_type": "telegram",
        "channel_conversation_id": "c1",
        "channel_message_id": "m1",
        "text": "hello",
        "timestamp": datetime.utcnow(),
        "metadata": {"k": "v"},
    }
    msg = IncomingMessage(**payload)
    assert msg.channel_type == "telegram"
    assert msg.text == "hello"
    assert msg.metadata == {"k": "v"}


@pytest.mark.asyncio
async def test_pipeline_process_runs_all_steps_and_sets_outgoing():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(
            content="ok",
            model="gpt-4o",
            usage={"total_tokens": 1},
            raw={},
        )
    )
    pipeline = MessagePipeline(brain=brain)

    incoming = IncomingMessage(
        channel_type="umnico",
        channel_conversation_id="conv-1",
        channel_message_id="msg-1",
        text="Сколько стоит?",
    )
    ctx = PipelineContext(
        incoming=incoming,
        agent_config=_make_agent_config(),
        knowledge={"pricing": "4990"},
        dialogue_policy=DialoguePolicyConfig(),
    )

    out = await pipeline.process(ctx)
    assert out.error is None
    assert out.outgoing is not None
    assert out.outgoing.text == "ok"


@pytest.mark.asyncio
async def test_pipeline_exception_stops_processing_and_sets_error():
    brain = AsyncMock()
    pipeline = MessagePipeline(brain=brain)

    pipeline._detect_intent = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    pipeline._pre_action = AsyncMock()  # type: ignore[method-assign]

    incoming = IncomingMessage(
        channel_type="telegram",
        channel_conversation_id="c1",
        channel_message_id="m1",
        text="hi",
    )
    ctx = PipelineContext(
        incoming=incoming,
        agent_config=_make_agent_config(),
        knowledge={},
        dialogue_policy=DialoguePolicyConfig(),
    )

    out = await pipeline.process(ctx)
    assert out.error is not None
    pipeline._pre_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_outgoing_contains_text_from_brain():
    brain = AsyncMock()
    brain.think = AsyncMock(
        return_value=BrainResponse(content="answer", model="m", usage={}, raw={})
    )
    pipeline = MessagePipeline(brain=brain)

    incoming = IncomingMessage(
        channel_type="telegram",
        channel_conversation_id="c1",
        channel_message_id="m1",
        text="hi",
    )
    ctx = PipelineContext(
        incoming=incoming,
        agent_config=_make_agent_config(),
        knowledge={},
        dialogue_policy=DialoguePolicyConfig(),
    )

    out = await pipeline.process(ctx)
    assert out.outgoing is not None
    assert out.outgoing.text == "answer"

