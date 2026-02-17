from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Numeric, and_, case, cast, func, select
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



class ReliabilityOverviewResponse(BaseModel):
    window_hours: int
    finalized_conversations: int
    created_count: int
    busy_count: int
    busy_escalated_count: int
    pending_manager_count: int
    booking_success_rate_pct: float | None
    busy_detection_precision_pct: float | None
    false_confirmation_count: int
    p95_latency_ms: float | None
    critical_incident_count: int


@router.get("/reliability", response_model=ReliabilityOverviewResponse)
async def reliability_overview(
    agent_id: UUID | None = Query(default=None),
    hours: int = Query(default=24, ge=1, le=24 * 90),
    db: AsyncSession = Depends(get_db),
) -> ReliabilityOverviewResponse:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    status_expr = cast(cast(Conversation.state, JSONB)["flow"]["booking_status"].astext, String)
    stage_expr = cast(cast(Conversation.state, JSONB)["flow"]["stage"].astext, String)

    finalized_q = select(func.count(Conversation.id)).where(stage_expr == "finalize", Conversation.updated_at >= since)
    if agent_id:
        finalized_q = finalized_q.where(Conversation.agent_id == agent_id)
    finalized_conversations = int((await db.execute(finalized_q)).scalar_one() or 0)

    def _status_count(status: str):
        q = select(func.count(Conversation.id)).where(
            status_expr == status,
            Conversation.updated_at >= since,
        )
        if agent_id:
            q = q.where(Conversation.agent_id == agent_id)
        return q

    created_count = int((await db.execute(_status_count("created"))).scalar_one() or 0)
    busy_count = int((await db.execute(_status_count("busy"))).scalar_one() or 0)
    busy_escalated_count = int((await db.execute(_status_count("busy_escalated"))).scalar_one() or 0)
    pending_manager_count = int((await db.execute(_status_count("pending_manager"))).scalar_one() or 0)

    denom = created_count + busy_count + busy_escalated_count
    booking_success_rate_pct = round((created_count / denom) * 100.0, 2) if denom > 0 else None

    lower_content = func.lower(Message.content)
    false_confirm_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.role == "assistant",
            Message.created_at >= since,
            (lower_content.like("%бронь подтвержд%") | lower_content.like("%бронирование подтвержд%") | lower_content.like("%ваша бронь%")),
            cast(cast(Message.metadata_, JSONB)["booking_event_id"].astext, String).is_(None),
        )
    )
    if agent_id:
        false_confirm_q = false_confirm_q.where(Conversation.agent_id == agent_id)
    false_confirmation_count = int((await db.execute(false_confirm_q)).scalar_one() or 0)

    latency_raw = cast(cast(Message.metadata_, JSONB)["latency_ms"].astext, String)
    p95_q = (
        select(func.percentile_cont(0.95).within_group(cast(latency_raw, Numeric)))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.role == "assistant",
            Message.created_at >= since,
            latency_raw.op("~")(r"^[0-9]+(\.[0-9]+)?$"),
        )
    )
    if agent_id:
        p95_q = p95_q.where(Conversation.agent_id == agent_id)
    try:
        p95_latency_raw = (await db.execute(p95_q)).scalar_one_or_none()
        p95_latency_ms = float(p95_latency_raw) if p95_latency_raw is not None else None
    except Exception:
        p95_latency_ms = None

    busy_reply_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.role == "assistant",
            Message.created_at >= since,
            lower_content.like("%слот%занят%"),
        )
    )
    busy_reply_with_state_q = busy_reply_q.where(status_expr.in_(["busy", "busy_escalated"]))
    if agent_id:
        busy_reply_q = busy_reply_q.where(Conversation.agent_id == agent_id)
        busy_reply_with_state_q = busy_reply_with_state_q.where(Conversation.agent_id == agent_id)

    busy_reply_total = int((await db.execute(busy_reply_q)).scalar_one() or 0)
    busy_reply_with_state = int((await db.execute(busy_reply_with_state_q)).scalar_one() or 0)
    busy_detection_precision_pct = (
        round((busy_reply_with_state / busy_reply_total) * 100.0, 2) if busy_reply_total > 0 else None
    )

    contract_viol = cast(cast(Message.metadata_, JSONB)["state_contract_violations"].astext, String)
    incident_q = (
        select(func.count(Message.id))
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.role == "assistant",
            Message.created_at >= since,
            contract_viol.is_not(None),
        )
    )
    if agent_id:
        incident_q = incident_q.where(Conversation.agent_id == agent_id)
    critical_incident_count = int((await db.execute(incident_q)).scalar_one() or 0)

    return ReliabilityOverviewResponse(
        window_hours=hours,
        finalized_conversations=finalized_conversations,
        created_count=created_count,
        busy_count=busy_count,
        busy_escalated_count=busy_escalated_count,
        pending_manager_count=pending_manager_count,
        booking_success_rate_pct=booking_success_rate_pct,
        busy_detection_precision_pct=busy_detection_precision_pct,
        false_confirmation_count=false_confirmation_count,
        p95_latency_ms=p95_latency_ms,
        critical_incident_count=critical_incident_count,
    )
