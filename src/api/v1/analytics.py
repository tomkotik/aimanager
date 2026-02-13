from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String

from src.db import get_db
from src.models import Conversation, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class TopIntent(BaseModel):
    intent: str
    count: int


class MessagesByDay(BaseModel):
    date: str
    user: int
    assistant: int


class ConversationsByChannel(BaseModel):
    channel: str
    count: int


class AnalyticsOverviewResponse(BaseModel):
    total_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    conversations_today: int
    messages_today: int
    top_intents: list[TopIntent]
    messages_by_day: list[MessagesByDay]
    conversations_by_channel: list[ConversationsByChannel]


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def overview(
    agent_id: UUID | None = Query(default=None),
    days: int = Query(default=7, ge=0, le=3650),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverviewResponse:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days) if days > 0 else None

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    conv_filters = []
    msg_filters = []
    if agent_id:
        conv_filters.append(Conversation.agent_id == agent_id)
        msg_filters.append(Conversation.agent_id == agent_id)
    if since:
        conv_filters.append(Conversation.created_at >= since)
        msg_filters.append(Message.created_at >= since)

    # Conversations in range.
    total_conv_q = select(func.count(Conversation.id))
    if conv_filters:
        total_conv_q = total_conv_q.where(and_(*conv_filters))
    total_conversations = int((await db.execute(total_conv_q)).scalar_one() or 0)

    # Messages in range (join to conversations for agent filter).
    total_msg_q = select(func.count(Message.id)).select_from(Message).join(
        Conversation, Message.conversation_id == Conversation.id
    )
    if msg_filters:
        total_msg_q = total_msg_q.where(and_(*msg_filters))
    total_messages = int((await db.execute(total_msg_q)).scalar_one() or 0)

    avg = float(total_messages / total_conversations) if total_conversations > 0 else 0.0

    # Today counts (UTC day).
    conv_today_filters = []
    msg_today_filters = []
    if agent_id:
        conv_today_filters.append(Conversation.agent_id == agent_id)
        msg_today_filters.append(Conversation.agent_id == agent_id)
    conv_today_filters.append(Conversation.created_at >= today_start)
    msg_today_filters.append(Message.created_at >= today_start)

    conv_today_q = select(func.count(Conversation.id)).where(and_(*conv_today_filters))
    conversations_today = int((await db.execute(conv_today_q)).scalar_one() or 0)

    msg_today_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(and_(*msg_today_filters))
    )
    messages_today = int((await db.execute(msg_today_q)).scalar_one() or 0)

    # Top intents (assistant messages only).
    intent_expr = cast(cast(Message.metadata_, JSONB)["intent"].astext, String)
    top_intents_q = (
        select(intent_expr.label("intent"), func.count(Message.id).label("cnt"))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.role == "assistant")
    )
    if agent_id:
        top_intents_q = top_intents_q.where(Conversation.agent_id == agent_id)
    if since:
        top_intents_q = top_intents_q.where(Message.created_at >= since)
    top_intents_q = top_intents_q.group_by(intent_expr).order_by(func.count(Message.id).desc()).limit(10)

    top_intents_rows = (await db.execute(top_intents_q)).all()
    top_intents = [
        TopIntent(intent=(row.intent or "UNKNOWN"), count=int(row.cnt or 0)) for row in top_intents_rows
    ]

    # Messages by day (user vs assistant).
    day_expr = func.date_trunc("day", Message.created_at).label("day")
    user_cnt = func.sum(case((Message.role == "user", 1), else_=0)).label("user_cnt")
    assistant_cnt = func.sum(case((Message.role == "assistant", 1), else_=0)).label("assistant_cnt")

    by_day_q = (
        select(day_expr, user_cnt, assistant_cnt)
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
    )
    if agent_id:
        by_day_q = by_day_q.where(Conversation.agent_id == agent_id)
    if since:
        by_day_q = by_day_q.where(Message.created_at >= since)
    by_day_q = by_day_q.group_by(day_expr).order_by(day_expr.asc())

    by_day_rows = (await db.execute(by_day_q)).all()
    messages_by_day = [
        MessagesByDay(
            date=row.day.date().isoformat(),
            user=int(row.user_cnt or 0),
            assistant=int(row.assistant_cnt or 0),
        )
        for row in by_day_rows
    ]

    # Conversations by channel.
    by_channel_q = select(Conversation.channel_type, func.count(Conversation.id)).group_by(Conversation.channel_type)
    if conv_filters:
        by_channel_q = by_channel_q.where(and_(*conv_filters))
    by_channel_q = by_channel_q.order_by(func.count(Conversation.id).desc())

    by_channel_rows = (await db.execute(by_channel_q)).all()
    conversations_by_channel = [
        ConversationsByChannel(channel=str(row[0]), count=int(row[1] or 0)) for row in by_channel_rows
    ]

    return AnalyticsOverviewResponse(
        total_conversations=total_conversations,
        total_messages=total_messages,
        avg_messages_per_conversation=avg,
        conversations_today=conversations_today,
        messages_today=messages_today,
        top_intents=top_intents,
        messages_by_day=messages_by_day,
        conversations_by_channel=conversations_by_channel,
    )

