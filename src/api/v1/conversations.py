from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models import Agent, Conversation, Message

from .schemas import (
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    PaginatedResponse,
)


router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.get(
    "/agents/{agent_id}/conversations",
    response_model=PaginatedResponse[ConversationResponse],
)
async def list_conversations(
    agent_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ConversationResponse]:
    agent_result = await db.execute(select(Agent.id).where(Agent.id == agent_id))
    if agent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    total_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.agent_id == agent_id)
    )
    total = int(total_result.scalar_one() or 0)

    counts_sq = (
        select(Message.conversation_id, func.count(Message.id).label("message_count"))
        .group_by(Message.conversation_id)
        .subquery()
    )

    result = await db.execute(
        select(Conversation, func.coalesce(counts_sq.c.message_count, 0))
        .outerjoin(counts_sq, counts_sq.c.conversation_id == Conversation.id)
        .where(Conversation.agent_id == agent_id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    items: list[ConversationResponse] = []
    for conv, msg_count in result.all():
        items.append(
            ConversationResponse(
                id=conv.id,
                channel_type=conv.channel_type,
                channel_conversation_id=conv.channel_conversation_id,
                lead_name=conv.lead_name,
                lead_phone=conv.lead_phone,
                is_active=conv.is_active,
                created_at=conv.created_at,
                message_count=int(msg_count or 0),
            )
        )

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = conv_result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    count_result = await db.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    msg_count = int(count_result.scalar_one() or 0)

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    conv_resp = ConversationResponse(
        id=conv.id,
        channel_type=conv.channel_type,
        channel_conversation_id=conv.channel_conversation_id,
        lead_name=conv.lead_name,
        lead_phone=conv.lead_phone,
        is_active=conv.is_active,
        created_at=conv.created_at,
        message_count=msg_count,
    )
    return ConversationDetailResponse(
        conversation=conv_resp,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                metadata=m.metadata_,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=PaginatedResponse[MessageResponse],
)
async def list_messages(
    conversation_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[MessageResponse]:
    conv_result = await db.execute(select(Conversation.id).where(Conversation.id == conversation_id))
    if conv_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    total_result = await db.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    total = int(total_result.scalar_one() or 0)

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            metadata=m.metadata_,
            created_at=m.created_at,
        )
        for m in msg_result.scalars().all()
    ]

    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)
