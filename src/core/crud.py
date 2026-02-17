from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.models import Agent, Conversation, Message, Tenant


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def create_tenant(db: AsyncSession, slug: str, name: str, owner_email: str, **kwargs) -> Tenant:
    tenant = Tenant(slug=slug, name=name, owner_email=owner_email, **kwargs)
    db.add(tenant)
    await db.flush()
    return tenant


async def get_agent(db: AsyncSession, tenant_id: UUID, agent_slug: str) -> Agent | None:
    result = await db.execute(select(Agent).where(Agent.tenant_id == tenant_id, Agent.slug == agent_slug))
    return result.scalar_one_or_none()


async def create_agent(
    db: AsyncSession,
    tenant_id: UUID,
    slug: str,
    name: str,
    config: dict,
    **kwargs,
) -> Agent:
    agent = Agent(tenant_id=tenant_id, slug=slug, name=name, config=config, **kwargs)
    db.add(agent)
    await db.flush()
    return agent


async def get_or_create_conversation(
    db: AsyncSession,
    agent_id: UUID,
    channel_type: str,
    channel_conversation_id: str,
) -> tuple[Conversation, bool]:
    """Return an existing conversation or create a new one. Returns (conversation, is_new)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.agent_id == agent_id,
            Conversation.channel_type == channel_type,
            Conversation.channel_conversation_id == channel_conversation_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv:
        return conv, False

    conv = Conversation(
        agent_id=agent_id,
        channel_type=channel_type,
        channel_conversation_id=channel_conversation_id,
        state={},
    )
    db.add(conv)
    await db.flush()
    return conv, True


async def get_conversation_history(db: AsyncSession, conversation_id: UUID, limit: int = 20) -> list[dict]:
    """Return conversation history in the format: [{"role": "...", "content": "..."}, ...]."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    messages.reverse()
    return [{"role": m.role, "content": m.content} for m in messages]


async def save_message(
    db: AsyncSession,
    conversation_id: UUID,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content, metadata_=metadata or {})
    db.add(msg)
    await db.flush()
    return msg


async def update_conversation_state(db: AsyncSession, conversation_id: UUID, state: dict) -> Conversation | None:
    """Persist conversation.state safely for nested JSON updates."""
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = result.scalar_one_or_none()
    if conv is None:
        return None

    current = conv.state if isinstance(conv.state, dict) else {}

    # Merge top-level keys to avoid accidental state wipe by partial updates.
    merged = dict(current)
    merged.update(state or {})

    conv.state = merged
    flag_modified(conv, "state")
    await db.flush()
    return conv
