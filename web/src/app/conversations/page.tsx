"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/ToastProvider";
import { apiFetch, formatApiErrorRu } from "@/lib/api";
import {
  AgentResponse,
  ConversationDetailResponse,
  ConversationResponse,
  MessageResponse,
  PaginatedResponse,
} from "@/types/api";

type ChannelFilter = "all" | string;
type ActiveFilter = "all" | "active" | "stopped";

function channelIcon(channel: string): string {
  if (channel === "umnico") return "🟦";
  if (channel === "telegram") return "🟦";
  if (channel === "test_chat") return "🧪";
  return "💬";
}

function channelLabel(channel: string): string {
  if (channel === "test_chat") return "Тестовый чат";
  if (channel === "umnico") return "Umnico";
  if (channel === "telegram") return "Telegram";
  return channel;
}

function roleBubbleClasses(role: string): { wrap: string; bubble: string } {
  if (role === "assistant") {
    return {
      wrap: "justify-end",
      bubble: "bg-accent text-black border border-accent/40",
    };
  }
  return {
    wrap: "justify-start",
    bubble: "bg-bg-hover text-text border border-border",
  };
}

function safeObject(v: unknown): Record<string, unknown> | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  return v as Record<string, unknown>;
}

function extractLastSnippet(content: string): string {
  const trimmed = content.trim().replace(/\s+/g, " ");
  if (trimmed.length <= 80) return trimmed;
  return `${trimmed.slice(0, 77)}...`;
}

export default function ConversationsPage() {
  const toast = useToast();

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [agentId, setAgentId] = useState<string>("");

  const [items, setItems] = useState<ConversationResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const limit = 20;

  const [loadingList, setLoadingList] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const [selectedConversationId, setSelectedConversationId] = useState<string>("");
  const [detail, setDetail] = useState<ConversationDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [channelFilter, setChannelFilter] = useState<ChannelFilter>("all");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all");

  const [lastByConversation, setLastByConversation] = useState<
    Record<string, { snippet: string; at: string }>
  >({});

  const [selectedMessage, setSelectedMessage] = useState<MessageResponse | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  async function loadAgents() {
    try {
      const list = await apiFetch<AgentResponse[]>("/api/v1/agents");
      setAgents(list);
      if (!agentId && list.length > 0) setAgentId(list[0].id);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки агентов",
        message: formatApiErrorRu(e),
      });
    }
  }

  async function loadConversations(reset: boolean) {
    if (!agentId) return;
    try {
      if (reset) {
        setLoadingList(true);
        setOffset(0);
      } else {
        setLoadingMore(true);
      }

      const nextOffset = reset ? 0 : offset;
      const res = await apiFetch<PaginatedResponse<ConversationResponse>>(
        `/api/v1/agents/${agentId}/conversations?limit=${limit}&offset=${nextOffset}`
      );
      setTotal(res.total);
      setItems((prev) => (reset ? res.items : [...prev, ...res.items]));
      setOffset(nextOffset + res.items.length);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки диалогов",
        message: formatApiErrorRu(e),
      });
    } finally {
      setLoadingList(false);
      setLoadingMore(false);
    }
  }

  async function loadLastMessage(conversationId: string) {
    try {
      const res = await apiFetch<PaginatedResponse<MessageResponse>>(
        `/api/v1/conversations/${conversationId}/messages?limit=1&offset=0`
      );
      const msg = res.items[0];
      if (!msg) return;
      setLastByConversation((prev) => ({
        ...prev,
        [conversationId]: { snippet: extractLastSnippet(msg.content), at: msg.created_at },
      }));
    } catch {
      // Ignore per-item failure.
    }
  }

  async function loadConversationDetail(conversationId: string) {
    try {
      setLoadingDetail(true);
      const res = await apiFetch<ConversationDetailResponse>(`/api/v1/conversations/${conversationId}`);
      setDetail(res);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки диалога",
        message: formatApiErrorRu(e),
      });
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => {
    void loadAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!agentId) return;
    setSelectedConversationId("");
    setDetail(null);
    setSelectedMessage(null);
    setLastByConversation({});
    void loadConversations(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  // Lazy-load last message snippets for list items.
  useEffect(() => {
    const missing = items.filter((c) => !lastByConversation[c.id]);
    if (missing.length === 0) return;
    for (const c of missing.slice(0, 8)) {
      void loadLastMessage(c.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (!detail) return;
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.messages?.length]);

  // Polling every 5 seconds.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (selectedConversationId) {
        void loadConversationDetail(selectedConversationId);
        void loadLastMessage(selectedConversationId);
      }
      if (agentId) {
        // Refresh the first page for updated ordering/counts.
        void loadConversations(true);
      }
    }, 5000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, selectedConversationId, offset]);

  const availableChannels = useMemo(() => {
    const s = new Set<string>();
    items.forEach((c) => s.add(c.channel_type));
    return Array.from(s).sort();
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((c) => {
      if (channelFilter !== "all" && c.channel_type !== channelFilter) return false;
      if (activeFilter === "active" && !c.is_active) return false;
      if (activeFilter === "stopped" && c.is_active) return false;
      return true;
    });
  }, [items, channelFilter, activeFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">Диалоги</h1>
          <div className="mt-1 text-sm text-text-dim">
            Просмотр переписок агента (обновление каждые 5 секунд)
          </div>
        </div>
      </div>

      <Card className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="text-xs text-text-dim">Выберите агента</div>
          <select
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            className="w-full md:w-[420px] rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.slug})
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="text-xs text-text-dim">Канал</div>
          <select
            value={channelFilter}
            onChange={(e) => setChannelFilter(e.target.value)}
            className="w-full md:w-48 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
          >
            <option value="all">Все каналы</option>
            {availableChannels.map((ch) => (
              <option key={ch} value={ch}>
                {channelLabel(ch)}
              </option>
            ))}
          </select>

          <div className="text-xs text-text-dim">Статус</div>
          <select
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value as ActiveFilter)}
            className="w-full md:w-48 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
          >
            <option value="all">Все</option>
            <option value="active">Активные</option>
            <option value="stopped">Завершённые</option>
          </select>

          <Button variant="secondary" onClick={() => void loadConversations(true)} disabled={loadingList}>
            Обновить
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-sm">Список</div>
            <div className="text-xs text-text-dim">
              {filtered.length}/{total}
            </div>
          </div>

          <div className="mt-3 space-y-2">
            {loadingList ? (
              <div className="space-y-2">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="h-14 rounded-lg bg-border/40 animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="text-sm text-text-dim">Нет диалогов.</div>
            ) : (
              filtered.map((c) => {
                const last = lastByConversation[c.id];
                const active = c.id === selectedConversationId;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      setSelectedConversationId(c.id);
                      setSelectedMessage(null);
                      void loadConversationDetail(c.id);
                      void loadLastMessage(c.id);
                    }}
                    className={[
                      "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                      active ? "border-border-light bg-bg-hover" : "border-border hover:bg-bg-hover",
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex items-center gap-2">
                        <span className="text-xs">{channelIcon(c.channel_type)}</span>
                        <div className="truncate text-sm text-text">
                          {c.lead_name || "Без имени"}
                        </div>
                      </div>
                      <div className="text-xs text-text-dim">
                        {last ? new Date(last.at).toLocaleTimeString() : ""}
                      </div>
                    </div>
                    <div className="mt-1 truncate text-xs text-text-muted">
                      {last ? last.snippet : `сообщ.: ${c.message_count}`}
                    </div>
                  </button>
                );
              })
            )}

            {items.length < total ? (
              <div className="pt-2">
                <Button
                  variant="secondary"
                  onClick={() => void loadConversations(false)}
                  disabled={loadingMore || loadingList}
                  className="w-full"
                >
                  {loadingMore ? "Загрузка..." : "Загрузить ещё"}
                </Button>
              </div>
            ) : null}
          </div>
        </Card>

        <Card className="lg:col-span-8">
          {!selectedConversationId ? (
            <div className="text-sm text-text-dim">Выберите диалог слева.</div>
          ) : loadingDetail || !detail ? (
            <div className="h-64 rounded-lg bg-border/40 animate-pulse" />
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="lg:col-span-8">
                <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
                  <div className="min-w-0">
                    <div className="truncate font-mono text-sm">
                      {detail.conversation.lead_name || "Без имени"}
                    </div>
                    <div className="mt-1 text-xs text-text-dim">
                      {channelLabel(detail.conversation.channel_type)} ·{" "}
                      {detail.conversation.lead_phone || "телефон не указан"}
                    </div>
                  </div>
                  <div className="text-xs text-text-dim">
                    {detail.conversation.is_active ? "Активный" : "Завершённый"}
                  </div>
                </div>

                <div className="mt-4 max-h-[560px] overflow-auto pr-1">
                  <div className="flex flex-col gap-2">
                    {detail.messages.map((m) => {
                      const cls = roleBubbleClasses(m.role);
                      return (
                        <div key={m.id} className={`flex ${cls.wrap}`}>
                          <button
                            type="button"
                            onClick={() => setSelectedMessage(m)}
                            className={[
                              "max-w-[85%] rounded-xl px-3 py-2 text-left text-sm transition-colors",
                              cls.bubble,
                              "hover:brightness-110",
                            ].join(" ")}
                          >
                            <div className="whitespace-pre-wrap">{m.content}</div>
                            <div className="mt-1 text-[11px] opacity-70">
                              {new Date(m.created_at).toLocaleString()}
                            </div>
                          </button>
                        </div>
                      );
                    })}
                    <div ref={chatEndRef} />
                  </div>
                </div>
              </div>

              <div className="lg:col-span-4">
                <div className="rounded-xl border border-border bg-bg p-3">
                  <div className="font-mono text-sm">Детали сообщения</div>
                  {!selectedMessage ? (
                    <div className="mt-2 text-xs text-text-dim">Нажмите на сообщение.</div>
                  ) : (
                    <MessageMeta message={selectedMessage} />
                  )}
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function MessageMeta({ message }: { message: MessageResponse }) {
  const meta = safeObject(message.metadata);
  const intent = meta ? String(meta.intent || "") : "";
  const model = meta ? String(meta.model || "") : "";
  const usage = meta ? safeObject(meta.usage) : null;

  const tokens =
    usage && typeof usage.total_tokens === "number"
      ? usage.total_tokens
      : usage && typeof usage.totalTokens === "number"
        ? usage.totalTokens
        : null;

  return (
    <div className="mt-3 space-y-3 text-xs text-text-muted">
      <div>
        <div className="text-text-dim">Роль</div>
        <div className="font-mono text-text">
          {message.role === "user" ? "Клиент" : message.role === "assistant" ? "Агент" : message.role}
        </div>
      </div>
      <div>
        <div className="text-text-dim">Намерение</div>
        <div className="font-mono text-text">{intent || "-"}</div>
      </div>
      <div>
        <div className="text-text-dim">Модель</div>
        <div className="font-mono text-text">{model || "-"}</div>
      </div>
      <div>
        <div className="text-text-dim">Токены</div>
        <div className="font-mono text-text">{tokens !== null ? String(tokens) : "-"}</div>
      </div>
    </div>
  );
}
