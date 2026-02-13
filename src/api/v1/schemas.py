from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    tenant_id: UUID
    is_active: bool
    created_at: datetime


class AgentDetailResponse(AgentResponse):
    config: dict
    dialogue_policy: dict
    actions_config: dict


class AgentCreateRequest(BaseModel):
    tenant_slug: str
    agent_slug: str
    name: str | None = None
    config: dict | None = None


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    dialogue_policy: dict | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    is_active: bool
    created_at: datetime


class ConversationResponse(BaseModel):
    id: UUID
    channel_type: str
    channel_conversation_id: str
    lead_name: str | None
    lead_phone: str | None
    is_active: bool
    created_at: datetime
    message_count: int = 0


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    metadata: dict | None
    created_at: datetime


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class ConversationDetailResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse] = Field(default_factory=list)
