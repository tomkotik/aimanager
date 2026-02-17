from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AgentIdentity(BaseModel):
    role: str
    persona: str
    fallback_phrase: str = "Чем могу помочь?"


class AgentStyle(BaseModel):
    tone: str = "warm_professional"
    politeness: str = "вы"
    emoji_policy: str = "rare"
    greeting: str = ""
    clean_text: bool = True
    max_sentences: int = 3
    max_questions: int = 1


class AgentRule(BaseModel):
    id: str
    priority: str = "normal"
    description: str
    positive_example: Optional[str] = None
    negative_example: Optional[str] = None


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_history: int = 20


class ChannelConfig(BaseModel):
    type: str
    config: dict = Field(default_factory=dict)


class AgentConfig(BaseModel):
    id: str
    name: str
    schema_version: str = "1.1.0"
    identity: AgentIdentity
    style: AgentStyle = Field(default_factory=AgentStyle)
    rules: list[AgentRule] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    channels: list[ChannelConfig] = Field(default_factory=list)
    runtime: dict = Field(default_factory=dict)


class IntentContract(BaseModel):
    must_include_any: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class IntentConfig(BaseModel):
    id: str
    markers: list[str]
    priority: int = 50
    contract: Optional[IntentContract] = None


class ConversationStage(BaseModel):
    id: str
    goal: str
    required_fields: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class DialoguePolicyConfig(BaseModel):
    intents: list[IntentConfig] = Field(default_factory=list)
    conversation_flow: dict = Field(default_factory=dict)


class ActionConfig(BaseModel):
    id: str
    type: str
    trigger: str
    config: dict = Field(default_factory=dict)


class TenantFullConfig(BaseModel):
    """Full tenant configuration assembled from YAML and knowledge base files."""

    agent: AgentConfig
    dialogue_policy: DialoguePolicyConfig = Field(default_factory=DialoguePolicyConfig)
    actions: list[ActionConfig] = Field(default_factory=list)
    knowledge: dict[str, str] = Field(default_factory=dict)
