"""
Webhook endpoints for channel adapters that use push-based delivery.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.telegram import TelegramAdapter
from src.core.secrets import resolve_secret
from src.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/telegram/{agent_id}")
async def telegram_webhook(
    agent_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive Telegram Bot webhook updates.

    URL pattern: POST /api/v1/webhooks/telegram/{agent_id}
    """
    payload = await request.json()

    incoming = TelegramAdapter.parse_webhook(payload)
    if incoming is None:
        return {"ok": True, "skipped": True}

    try:
        # 1. Load agent from DB.
        from sqlalchemy import select

        from src.models import Agent, Tenant

        result = await db.execute(
            select(Agent, Tenant)
            .join(Tenant, Agent.tenant_id == Tenant.id)
            .where(Agent.id == agent_id, Agent.is_active == True)  # noqa: E712
        )
        row = result.first()
        if not row:
            logger.warning("Telegram webhook: agent %s not found", agent_id)
            return {"ok": True, "error": "agent_not_found"}

        agent, tenant = row

        # 2. Load tenant config.
        from src.core.config_loader import load_tenant_config

        tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")

        # 3. Resolve secrets.
        api_key = resolve_secret(tenant.slug, "openai_key")

        # 4. Build pipeline context.
        from src.core.brain import Brain
        from src.core.crud import (
            get_conversation_history,
            get_or_create_conversation,
            save_message,
        )
        from src.core.pipeline import MessagePipeline, PipelineContext

        incoming.metadata["agent_id"] = str(agent.id)

        conv, is_new = await get_or_create_conversation(
            db,
            agent_id=agent.id,
            channel_type="telegram",
            channel_conversation_id=incoming.channel_conversation_id,
        )

        history = [] if is_new else await get_conversation_history(db, conv.id)
        incoming.metadata["conversation_state"] = conv.state or {}
        incoming.metadata["conversation_id"] = str(conv.id)

        ctx = PipelineContext(
            incoming=incoming,
            agent_config=tenant_cfg.agent,
            knowledge=tenant_cfg.knowledge,
            dialogue_policy=tenant_cfg.dialogue_policy,
            history=history,
        )

        # 5. Process.
        brain = Brain.from_config(tenant_cfg.agent.llm, api_key=api_key)
        pipeline = MessagePipeline(brain=brain, db_session=db)
        ctx = await pipeline.process(ctx)

        if ctx.error:
            logger.error("Webhook pipeline error: %s", ctx.error)
            return {"ok": True, "error": ctx.error}

        # 6. Send reply.
        if ctx.outgoing and ctx.outgoing.text:
            tg_token = resolve_secret(tenant.slug, "telegram_bot_token")
            tg_config = next(
                (
                    ch.get("config", {})
                    for ch in (agent.config or {}).get("channels", [])
                    if ch.get("type") == "telegram"
                ),
                {},
            )
            tg_config = {**tg_config}
            tg_config["token"] = tg_token or tg_config.get("token", "")

            adapter = TelegramAdapter(tg_config)
            sent = await adapter.send(incoming.channel_conversation_id, ctx.outgoing.text)

            if sent:
                await save_message(db, conv.id, "user", incoming.text)
                await save_message(
                    db,
                    conv.id,
                    "assistant",
                    ctx.outgoing.text,
                    metadata=ctx.outgoing.metadata,
                )
                conv.state = incoming.metadata.get("conversation_state", {})
                if incoming.sender_name and not conv.lead_name:
                    conv.lead_name = incoming.sender_name

        return {"ok": True}
    except Exception as e:
        logger.exception("Telegram webhook error for agent %s: %s", agent_id, e)
        return {"ok": True, "error": str(e)}
