"""
Polling Worker — Celery task that periodically checks poll-based channels for new messages.

Workflow per tick:
1. Load all active agents from DB
2. For each agent, find poll-based channels (e.g., Umnico)
3. For each channel, call adapter.receive() to get new messages
4. For each new message (not yet processed):
   a. Get or create conversation in DB
   b. Build PipelineContext
   c. Run Pipeline.process()
   d. Send reply via channel adapter
   e. Save messages (user + assistant) to DB
"""

from __future__ import annotations

import asyncio
import logging

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# State: track last processed message per conversation to avoid duplicates.
# In production, this should be in Redis. For now, in-memory dict.
_last_message_ids: dict[str, str] = {}

# Keep one asyncio loop per worker process. Creating a new loop for each Celery tick
# causes asyncpg/SQLAlchemy "attached to a different loop" and "another operation in progress".
_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    return _worker_loop


@celery_app.task(name="agentbox.poll_channels")
def poll_channels_task():
    """
    Celery task entry point. Runs the async polling logic.

    Scheduled via celery beat (every 3-5 seconds).
    """
    loop = _get_worker_loop()
    loop.run_until_complete(_poll_channels())


async def _poll_channels():
    """
    Main polling loop (single tick).

    1. Query all active agents from DB
    2. For each agent with poll-based channels -> fetch messages -> process -> reply
    """
    from sqlalchemy import select

    # Import channel modules for registration side effects.
    # Poller uses `get_channel_adapter()`, which relies on CHANNEL_REGISTRY being populated.
    import src.channels.umnico  # noqa: F401

    from src.channels import get_channel_adapter
    from src.core.brain import Brain
    from src.core.config_loader import load_tenant_config
    from src.core.secrets import resolve_secret
    from src.core.crud import (
        get_conversation_history,
        get_or_create_conversation,
        save_message,
    )
    from src.core.pipeline import MessagePipeline, PipelineContext
    from src.db import async_session
    from src.models import Agent, Tenant

    async with async_session() as db:
        # 1. Load active agents.
        result = await db.execute(
            select(Agent, Tenant)
            .join(Tenant, Agent.tenant_id == Tenant.id)
            .where(Agent.is_active == True)  # noqa: E712
        )
        rows = result.all()

        for agent, tenant in rows:
            agent_config_dict = agent.config or {}
            channels = agent_config_dict.get("channels", [])

            # Filter poll-based channels.
            poll_channels = [ch for ch in channels if ch.get("type") in ("umnico",)]

            for ch_config in poll_channels:
                try:
                    umnico_token = (
                        resolve_secret(tenant.slug, "umnico_api_token")
                        or resolve_secret(tenant.slug, "umnico_token")
                    )
                    if not umnico_token:
                        logger.warning("Umnico token missing for tenant=%s; skip polling", tenant.slug)
                        continue

                    ch_config_resolved = {**ch_config.get("config", {}), "token": umnico_token}
                    adapter = get_channel_adapter(ch_config["type"], ch_config_resolved)
                    messages = await adapter.receive()

                    for msg in messages:
                        # Dedup: skip if we already processed this message.
                        dedup_key = f"{agent.id}:{msg.channel_conversation_id}"
                        if _last_message_ids.get(dedup_key) == msg.channel_message_id:
                            continue
                        _last_message_ids[dedup_key] = msg.channel_message_id

                        # Get or create conversation.
                        conv, is_new = await get_or_create_conversation(
                            db,
                            agent_id=agent.id,
                            channel_type=msg.channel_type,
                            channel_conversation_id=msg.channel_conversation_id,
                        )

                        # Load history.
                        history = await get_conversation_history(
                            db,
                            conv.id,
                            limit=agent_config_dict.get("llm", {}).get("max_history", 20),
                        )

                        # Load tenant config for knowledge base.
                        tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")

                        # Build context.
                        msg.metadata["conversation_state"] = conv.state or {}

                        ctx = PipelineContext(
                            incoming=msg,
                            agent_config=tenant_cfg.agent,
                            knowledge=tenant_cfg.knowledge,
                            dialogue_policy=tenant_cfg.dialogue_policy,
                            history=history,
                        )

                        # Create brain and pipeline.
                        api_key = resolve_secret(tenant.slug, "openai_key")
                        brain = Brain.from_config(tenant_cfg.agent.llm, api_key=api_key)
                        pipeline = MessagePipeline(brain=brain, db_session=db)

                        # Process.
                        ctx = await pipeline.process(ctx)

                        if ctx.error:
                            logger.error(
                                "Pipeline error for agent %s, conv %s: %s",
                                agent.id,
                                conv.id,
                                ctx.error,
                            )
                            continue

                        # Send reply.
                        if ctx.outgoing and ctx.outgoing.text:
                            sent = await adapter.send(
                                msg.channel_conversation_id,
                                ctx.outgoing.text,
                            )

                            if sent:
                                # Save messages to DB.
                                await save_message(db, conv.id, "user", msg.text)
                                await save_message(
                                    db,
                                    conv.id,
                                    "assistant",
                                    ctx.outgoing.text,
                                    metadata=ctx.outgoing.metadata,
                                )

                                # Log lead to Google Sheets (optional, configured via actions.yaml).
                                from src.integrations.google_sheets import GoogleSheetsAdapter

                                sheets_actions = [a for a in tenant_cfg.actions if a.type == "google_sheets"]
                                if sheets_actions:
                                    sheets_config = {**sheets_actions[0].config}
                                    sa_path = resolve_secret(tenant.slug, "google_sa_path")
                                    if sa_path:
                                        sheets_config["service_account_path"] = sa_path
                                    sheets = GoogleSheetsAdapter(sheets_config)
                                    await sheets.execute(
                                        "append_lead",
                                        {
                                            "channel": msg.channel_type,
                                            "name": msg.sender_name or "",
                                            "contact": msg.sender_phone or "",
                                            "message": msg.text,
                                        },
                                    )

                                # Update conversation state.
                                conv.state = msg.metadata.get("conversation_state", {})

                                # Update lead info if available.
                                if msg.sender_name and not conv.lead_name:
                                    conv.lead_name = msg.sender_name
                                if msg.sender_phone and not conv.lead_phone:
                                    conv.lead_phone = msg.sender_phone

                                await db.flush()

                        logger.info(
                            "Processed message for agent %s: [%s] -> %s",
                            agent.slug,
                            msg.text[:30],
                            (ctx.outgoing.text[:30] + "...") if ctx.outgoing else "(no reply)",
                        )

                except Exception as e:
                    logger.exception(
                        "Polling error for agent %s, channel %s: %s",
                        agent.id,
                        ch_config.get("type"),
                        e,
                    )

        await db.commit()


# --- Celery Beat Schedule ---

celery_app.conf.beat_schedule = {
    "poll-channels-every-5s": {
        "task": "agentbox.poll_channels",
        "schedule": 5.0,
    },
}
