from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config_loader import load_tenant_config
from src.core.config_schema import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    get_config_schema_descriptor,
    migrate_agent_config,
)
from src.core.crud import create_agent, create_tenant, get_agent, get_tenant_by_slug
from src.core.secrets import resolve_secret
from src.db import get_db
from src.models import Agent, Conversation, Tenant

from .schemas import AgentCreateRequest, AgentDetailResponse, AgentResponse, AgentUpdateRequest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class ConfigSchemaResponse(BaseModel):
    current_version: str
    supported_versions: list[str]
    migrations: list[dict]


class ConfigMigrateRequest(BaseModel):
    config: dict


class ConfigMigrateResponse(BaseModel):
    from_version: str
    to_version: str
    migrated: dict


@router.get("/config/schema", response_model=ConfigSchemaResponse)
async def get_config_schema() -> ConfigSchemaResponse:
    descriptor = get_config_schema_descriptor()
    return ConfigSchemaResponse(**descriptor)


@router.post("/config/migrate", response_model=ConfigMigrateResponse)
async def migrate_config(payload: ConfigMigrateRequest) -> ConfigMigrateResponse:
    from_version = str(payload.config.get("schema_version", "1.0.0"))
    migrated = migrate_agent_config(payload.config)
    return ConfigMigrateResponse(
        from_version=from_version,
        to_version=str(migrated.get("schema_version", CURRENT_CONFIG_SCHEMA_VERSION)),
        migrated=migrated,
    )


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)) -> list[AgentResponse]:
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    agents = result.scalars().all()
    return [AgentResponse.model_validate(a) for a in agents]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_endpoint(
    payload: AgentCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    tenant_slug = payload.tenant_slug.strip()
    agent_slug = payload.agent_slug.strip()

    tenant = await get_tenant_by_slug(db, tenant_slug)

    tenant_cfg = None
    if tenant is None:
        # If we create an agent from YAML and the tenant config folder does not exist,
        # fail with a clear message (so the UI can explain the problem).
        if payload.config is None:
            agent_yaml = Path("tenants") / tenant_slug / "agent.yaml"
            if not agent_yaml.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant config not found: {agent_yaml.as_posix()}",
                )
            try:
                tenant_cfg = load_tenant_config(agent_yaml.parent)
            except Exception as e:
                logger.exception("Failed to load tenant config from %s", agent_yaml.parent)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid tenant config: {agent_yaml.parent.as_posix()}",
                ) from e

        # Auto-create tenant in DB so the web panel can work on a clean database.
        tenant = await create_tenant(db, slug=tenant_slug, name=tenant_slug, owner_email="")

    existing = await get_agent(db, tenant.id, agent_slug)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent already exists")

    config: dict
    name: str
    dialogue_policy: dict = {}
    actions_config: dict = {}

    if payload.config is None:
        if tenant_cfg is None:
            try:
                agent_yaml = Path("tenants") / tenant_slug / "agent.yaml"
                if not agent_yaml.exists():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Tenant config not found: {agent_yaml.as_posix()}",
                    )
                tenant_cfg = load_tenant_config(agent_yaml.parent)
            except FileNotFoundError as e:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
            except Exception as e:
                logger.exception("Failed to load tenant config from tenants/%s", tenant_slug)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid tenant config: tenants/{tenant_slug}",
                ) from e

        config = migrate_agent_config(tenant_cfg.agent.model_dump())
        name = payload.name or tenant_cfg.agent.name
        dialogue_policy = tenant_cfg.dialogue_policy.model_dump()
        actions_config = {"actions": [a.model_dump() for a in tenant_cfg.actions]}
    else:
        config = migrate_agent_config(payload.config)
        name = payload.name or agent_slug

    try:
        agent = await create_agent(
            db,
            tenant_id=tenant.id,
            slug=agent_slug,
            name=name,
            config=config,
            dialogue_policy=dialogue_policy,
            actions_config=actions_config,
        )
    except IntegrityError as e:
        # A second safety net for race conditions vs. the explicit pre-check above.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent already exists") from e
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent_endpoint(agent_id: UUID, db: AsyncSession = Depends(get_db)) -> AgentDetailResponse:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return AgentDetailResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentDetailResponse)
async def update_agent_endpoint(
    agent_id: UUID,
    payload: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentDetailResponse:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    if payload.name is not None:
        agent.name = payload.name
    if payload.config is not None:
        agent.config = migrate_agent_config(payload.config)
    if payload.dialogue_policy is not None:
        agent.dialogue_policy = payload.dialogue_policy
    if payload.is_active is not None:
        agent.is_active = payload.is_active

    await db.flush()
    return AgentDetailResponse.model_validate(agent)


@router.delete("/{agent_id}", response_model=AgentResponse)
async def delete_agent_endpoint(agent_id: UUID, db: AsyncSession = Depends(get_db)) -> AgentResponse:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.is_active = False
    await db.flush()
    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/sync", response_model=AgentResponse)
async def sync_agent_endpoint(agent_id: UUID, db: AsyncSession = Depends(get_db)) -> AgentResponse:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    t_result = await db.execute(select(Tenant).where(Tenant.id == agent.tenant_id))
    tenant = t_result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")
    agent.name = tenant_cfg.agent.name
    agent.config = migrate_agent_config(tenant_cfg.agent.model_dump())
    agent.dialogue_policy = tenant_cfg.dialogue_policy.model_dump()
    agent.actions_config = {"actions": [a.model_dump() for a in tenant_cfg.actions]}

    await db.flush()
    logger.info("Synced agent %s from YAML (%s)", agent.id, tenant.slug)

    return AgentResponse.model_validate(agent)


class AgentChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class AgentChatResponse(BaseModel):
    reply: str
    conversation_id: str
    intent: str | None
    contract_violations: list[str]
    model: str
    tokens_used: int


@router.post("/{agent_id}/chat", response_model=AgentChatResponse)
async def agent_chat(
    agent_id: UUID,
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
) -> AgentChatResponse:
    """
    Test chat endpoint: runs message through the real Pipeline without external channels.

    Saves both user and assistant messages to DB under channel_type="test_chat".
    """
    from uuid import UUID as UUIDType, uuid4

    # 1. Load agent and tenant.
    result = await db.execute(
        select(Agent, Tenant)
        .join(Tenant, Agent.tenant_id == Tenant.id)
        .where(Agent.id == agent_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent, tenant = row

    # 2. Resolve or create a test_chat channel_conversation_id.
    channel_conversation_id: str
    if payload.conversation_id:
        try:
            conv_uuid = UUIDType(payload.conversation_id)
        except ValueError:
            conv_uuid = None

        if conv_uuid:
            conv_result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conv_uuid,
                    Conversation.agent_id == agent.id,
                    Conversation.channel_type == "test_chat",
                )
            )
            conv = conv_result.scalar_one_or_none()
            if conv:
                channel_conversation_id = conv.channel_conversation_id
            else:
                channel_conversation_id = str(uuid4())
        else:
            channel_conversation_id = str(uuid4())
    else:
        channel_conversation_id = str(uuid4())

    # 3. Load tenant config.
    tenant_cfg = load_tenant_config(f"tenants/{tenant.slug}")

    # 4. Resolve OpenAI key.
    api_key = resolve_secret(tenant.slug, "openai_key")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret not configured: openai_key",
        )

    # 5. Build pipeline context.
    from src.core.brain import Brain
    from src.core.crud import save_message
    from src.core.pipeline import IncomingMessage, MessagePipeline, PipelineContext

    incoming = IncomingMessage(
        channel_type="test_chat",
        channel_conversation_id=channel_conversation_id,
        channel_message_id=str(uuid4()),
        text=payload.message,
        metadata={"agent_id": str(agent.id)},
    )

    ctx = PipelineContext(
        incoming=incoming,
        agent_config=tenant_cfg.agent,
        knowledge=tenant_cfg.knowledge,
        dialogue_policy=tenant_cfg.dialogue_policy,
        history=[],
    )

    # 6. Process.
    brain = Brain.from_config(tenant_cfg.agent.llm, api_key=api_key)
    pipeline = MessagePipeline(brain=brain, db_session=db)
    ctx = await pipeline.process(ctx)

    if ctx.error or not ctx.outgoing or not ctx.outgoing.text:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ctx.error or "No reply")

    # 7. Save messages and update state.
    conv_id = ctx.incoming.metadata.get("conversation_id", "")
    try:
        conv_uuid = UUIDType(str(conv_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid conversation_id")

    await save_message(db, conv_uuid, "user", incoming.text)
    await save_message(db, conv_uuid, "assistant", ctx.outgoing.text, metadata=ctx.outgoing.metadata)

    # Persist conversation state.
    state = ctx.incoming.metadata.get("conversation_state", {})
    if isinstance(state, dict):
        conv_result = await db.execute(select(Conversation).where(Conversation.id == conv_uuid))
        conv = conv_result.scalar_one_or_none()
        if conv:
            conv.state = state
            await db.flush()

    # Build response.
    usage = ctx.outgoing.metadata.get("usage") if isinstance(ctx.outgoing.metadata, dict) else None
    tokens_used = 0
    if isinstance(usage, dict):
        if isinstance(usage.get("total_tokens"), int):
            tokens_used = int(usage["total_tokens"])
        else:
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            if isinstance(pt, int) and isinstance(ct, int):
                tokens_used = int(pt + ct)

    violations: list[str] = []
    raw_violations = ctx.outgoing.metadata.get("contract_violations")
    if isinstance(raw_violations, list):
        violations = [str(v) for v in raw_violations]

    model = str(ctx.outgoing.metadata.get("model", "")) if isinstance(ctx.outgoing.metadata, dict) else ""

    return AgentChatResponse(
        reply=ctx.outgoing.text,
        conversation_id=str(conv_uuid),
        intent=ctx.detected_intent,
        contract_violations=violations,
        model=model,
        tokens_used=tokens_used,
    )
