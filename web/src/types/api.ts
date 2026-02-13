export type UUID = string;

export type AgentResponse = {
  id: UUID;
  slug: string;
  name: string;
  tenant_id: UUID;
  is_active: boolean;
  created_at: string;
};

export type AgentDetailResponse = AgentResponse & {
  config: Record<string, unknown>;
  dialogue_policy: Record<string, unknown>;
  actions_config: Record<string, unknown>;
};

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type ConversationResponse = {
  id: UUID;
  channel_type: string;
  channel_conversation_id: string;
  lead_name: string | null;
  lead_phone: string | null;
  is_active: boolean;
  created_at: string;
  message_count: number;
};

export type MessageResponse = {
  id: UUID;
  role: "user" | "assistant" | string;
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type ConversationDetailResponse = {
  conversation: ConversationResponse;
  messages: MessageResponse[];
};

export type KnowledgeFileInfo = {
  name: string;
  size: number;
  updated_at: string;
};

export type KnowledgeFileResponse = {
  name: string;
  content: string;
};

export type TenantResponse = {
  id: UUID;
  slug: string;
  name: string;
  is_active: boolean;
  created_at: string;
};

export type SecretInfo = {
  name: string;
  is_set: boolean;
  updated_at: string | null;
};

export type AnalyticsTopIntent = { intent: string; count: number };
export type AnalyticsMessagesByDay = { date: string; user: number; assistant: number };
export type AnalyticsConversationsByChannel = { channel: string; count: number };

export type AnalyticsOverviewResponse = {
  total_conversations: number;
  total_messages: number;
  avg_messages_per_conversation: number;
  conversations_today: number;
  messages_today: number;
  top_intents: AnalyticsTopIntent[];
  messages_by_day: AnalyticsMessagesByDay[];
  conversations_by_channel: AnalyticsConversationsByChannel[];
};

export type AgentChatResponse = {
  reply: string;
  conversation_id: UUID;
  intent: string | null;
  contract_violations: string[];
  model: string;
  tokens_used: number;
};
