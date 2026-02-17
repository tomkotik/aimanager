"""
Webhook endpoints for channel adapters that use push-based delivery.
"""

from __future__ import annotations

import hashlib
import json
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
        from pydantic import ValidationError
        from src.core.config_loader import AgentConfig, DialoguePolicyConfig, load_tenant_config

        tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")

        # 2.1 Runtime config source of truth:
        # - Use DB config edited in UI when available.
        # - Fallback to YAML when DB config is absent/invalid.
        agent_config = tenant_cfg.agent
        dialogue_policy = tenant_cfg.dialogue_policy

        if isinstance(agent.config, dict) and agent.config:
            try:
                agent_config = AgentConfig.model_validate(agent.config)
            except ValidationError:
                logger.warning("Invalid agent.config in DB for %s; fallback to YAML", agent.id)

        if isinstance(agent.dialogue_policy, dict) and agent.dialogue_policy:
            try:
                dialogue_policy = DialoguePolicyConfig.model_validate(agent.dialogue_policy)
            except ValidationError:
                logger.warning("Invalid agent.dialogue_policy in DB for %s; fallback to YAML", agent.id)

        # 2.2 Build config fingerprint for debugging/traceability.
        cfg_payload = {
            "agent": agent_config.model_dump(),
            "dialogue_policy": dialogue_policy.model_dump(),
        }
        config_version = hashlib.sha256(
            json.dumps(cfg_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]

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
        incoming.metadata["config_version"] = config_version

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
            agent_config=agent_config,
            knowledge=tenant_cfg.knowledge,
            dialogue_policy=dialogue_policy,
            history=history,
        )

        # 5. Process.
        brain = Brain.from_config(agent_config.llm, api_key=api_key)
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
                conv.state = json.loads(json.dumps(incoming.metadata.get("conversation_state", {}), ensure_ascii=False))
                if incoming.sender_name and not conv.lead_name:
                    conv.lead_name = incoming.sender_name

        return {"ok": True}
    except Exception as e:
        logger.exception("Telegram webhook error for agent %s: %s", agent_id, e)
        return {"ok": True, "error": str(e)}


@router.post("/umnico/{agent_id}")
async def umnico_webhook(
    agent_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive Umnico webhook events.

    URL pattern: POST /api/v1/webhooks/umnico/{agent_id}
    Umnico sends events for all integrations (WhatsApp, Telegram, Avito, etc.)
    connected in the Umnico account.
    """
    payload = await request.json()

    from src.channels.umnico import UmnicoAdapter

    incoming = UmnicoAdapter.parse_webhook(payload)
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
            logger.warning("Umnico webhook: agent %s not found", agent_id)
            return {"ok": True, "error": "agent_not_found"}

        agent, tenant = row

        # 2. Load tenant config.
        from pydantic import ValidationError
        from src.core.config_loader import AgentConfig, DialoguePolicyConfig, load_tenant_config

        tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")

        agent_config = tenant_cfg.agent
        dialogue_policy = tenant_cfg.dialogue_policy

        if isinstance(agent.config, dict) and agent.config:
            try:
                agent_config = AgentConfig.model_validate(agent.config)
            except ValidationError:
                logger.warning("Invalid agent.config in DB for %s; fallback to YAML", agent.id)

        if isinstance(agent.dialogue_policy, dict) and agent.dialogue_policy:
            try:
                dialogue_policy = DialoguePolicyConfig.model_validate(agent.dialogue_policy)
            except ValidationError:
                logger.warning("Invalid agent.dialogue_policy in DB for %s; fallback to YAML", agent.id)

        # 2.2 Config fingerprint.
        cfg_payload = {
            "agent": agent_config.model_dump(),
            "dialogue_policy": dialogue_policy.model_dump(),
        }
        config_version = hashlib.sha256(
            json.dumps(cfg_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]

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
        incoming.metadata["config_version"] = config_version

        conv, is_new = await get_or_create_conversation(
            db,
            agent_id=agent.id,
            channel_type="umnico",
            channel_conversation_id=incoming.channel_conversation_id,
        )

        history = [] if is_new else await get_conversation_history(db, conv.id)
        incoming.metadata["conversation_state"] = conv.state or {}
        incoming.metadata["conversation_id"] = str(conv.id)

        ctx = PipelineContext(
            incoming=incoming,
            agent_config=agent_config,
            knowledge=tenant_cfg.knowledge,
            dialogue_policy=dialogue_policy,
            history=history,
        )

        # 5. Process.
        brain = Brain.from_config(agent_config.llm, api_key=api_key)
        pipeline = MessagePipeline(brain=brain, db_session=db)
        ctx = await pipeline.process(ctx)

        if ctx.error:
            logger.error("Umnico webhook pipeline error: %s", ctx.error)
            return {"ok": True, "error": ctx.error}

        # 6. Send reply via Umnico API.
        if ctx.outgoing and ctx.outgoing.text:
            umnico_token = resolve_secret(tenant.slug, "umnico_api_token")
            if not umnico_token:
                logger.error("Umnico API token not found for tenant %s", tenant.slug)
                return {"ok": True, "error": "umnico_token_missing"}

            adapter = UmnicoAdapter({"api_token": umnico_token})
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
                conv.state = json.loads(json.dumps(incoming.metadata.get("conversation_state", {}), ensure_ascii=False))
                if incoming.sender_name and not conv.lead_name:
                    conv.lead_name = incoming.sender_name

                # Try to enrich lead info (phone, email) from Umnico.
                if not conv.lead_phone:
                    lead_info = await adapter.get_lead_info(incoming.channel_conversation_id)
                    if lead_info.get("phone"):
                        conv.lead_phone = lead_info["phone"]
                    if lead_info.get("name") and not conv.lead_name:
                        conv.lead_name = lead_info["name"]

        return {"ok": True}
    except Exception as e:
        logger.exception("Umnico webhook error for agent %s: %s", agent_id, e)
        return {"ok": True, "error": str(e)}
