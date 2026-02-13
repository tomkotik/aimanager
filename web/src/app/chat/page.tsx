"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/ToastProvider";
import { apiFetch, formatApiErrorRu } from "@/lib/api";
import { AgentChatResponse, AgentResponse } from "@/types/api";

type LocalMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

function bubble(role: LocalMessage["role"]): { wrap: string; bubble: string } {
  if (role === "user") {
    return { wrap: "justify-end", bubble: "bg-accent text-black border border-accent/40" };
  }
  return { wrap: "justify-start", bubble: "bg-bg-hover text-text border border-border" };
}

export default function ChatPage() {
  const toast = useToast();
  const endRef = useRef<HTMLDivElement | null>(null);

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [agentId, setAgentId] = useState<string>("");

  const [conversationId, setConversationId] = useState<string>("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);

  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const [debug, setDebug] = useState<{
    intent: string | null;
    contract_violations: string[];
    model: string;
    tokens_used: number;
    ms: number;
  } | null>(null);

  const selectedAgent = useMemo(() => agents.find((a) => a.id === agentId) || null, [agents, agentId]);

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

  useEffect(() => {
    void loadAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function send() {
    const text = input.trim();
    if (!text || !agentId) return;

    const now = new Date().toISOString();
    const localId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setMessages((prev) => [...prev, { id: localId, role: "user", content: text, created_at: now }]);
    setInput("");
    setLoading(true);

    const t0 = performance.now();
    try {
      const res = await apiFetch<AgentChatResponse>(`/api/v1/agents/${agentId}/chat`, {
        method: "POST",
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId || undefined,
        }),
      });

      const t1 = performance.now();
      setConversationId(res.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-a`,
          role: "assistant",
          content: res.reply,
          created_at: new Date().toISOString(),
        },
      ]);
      setDebug({
        intent: res.intent,
        contract_violations: res.contract_violations,
        model: res.model,
        tokens_used: res.tokens_used,
        ms: Math.round(t1 - t0),
      });
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка обработки",
        message: formatApiErrorRu(e, "Не удалось отправить сообщение"),
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">Тестовый чат</h1>
          <div className="mt-1 text-sm text-text-dim">
            Сообщение проходит через реальный Pipeline, без Umnico/Telegram
          </div>
        </div>
      </div>

      <Card className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <div className="text-xs text-text-dim">Агент</div>
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

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setConversationId("");
              setMessages([]);
              setDebug(null);
              toast.push({ variant: "info", title: "Новый диалог" });
            }}
          >
            Новый диалог
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-8">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="min-w-0">
              <div className="font-mono text-sm">
                {selectedAgent ? selectedAgent.name : "Агент не выбран"}
              </div>
              <div className="mt-1 text-xs text-text-dim">
                conversation_id: <span className="font-mono text-text-muted">{conversationId || "-"}</span>
              </div>
            </div>
            {loading ? (
              <div className="text-xs text-text-dim">Печатает...</div>
            ) : (
              <div className="text-xs text-text-dim">Готов</div>
            )}
          </div>

          <div className="mt-4 max-h-[540px] overflow-auto pr-1">
            <div className="flex flex-col gap-2">
              {messages.length === 0 ? (
                <div className="text-sm text-text-dim">Напишите сообщение ниже.</div>
              ) : null}
              {messages.map((m) => {
                const cls = bubble(m.role);
                return (
                  <div key={m.id} className={`flex ${cls.wrap}`}>
                    <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${cls.bubble}`}>
                      <div className="whitespace-pre-wrap">{m.content}</div>
                      <div className="mt-1 text-[11px] opacity-70">
                        {new Date(m.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
          </div>

          <div className="mt-4 border-t border-border pt-3">
            <div className="flex flex-col gap-2 md:flex-row md:items-end">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={2}
                disabled={loading || !agentId}
                className="flex-1 resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm font-mono outline-none focus:border-border-light disabled:opacity-50"
                placeholder="Сколько стоит?"
              />
              <Button variant="primary" onClick={() => void send()} disabled={loading || !agentId}>
                Отправить
              </Button>
            </div>
            <div className="mt-2 text-xs text-text-dim">
              Enter: отправить · Shift+Enter: новая строка
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-4">
          <div className="font-mono text-sm">Debug</div>
          <div className="mt-3 space-y-3 text-xs text-text-muted">
            <div>
              <div className="text-text-dim">intent</div>
              <div className="font-mono text-text">{debug?.intent || "-"}</div>
            </div>
            <div>
              <div className="text-text-dim">contract violations</div>
              {debug?.contract_violations && debug.contract_violations.length > 0 ? (
                <ul className="mt-1 list-disc pl-4">
                  {debug.contract_violations.map((v, idx) => (
                    <li key={idx}>{v}</li>
                  ))}
                </ul>
              ) : (
                <div className="font-mono text-text">-</div>
              )}
            </div>
            <div>
              <div className="text-text-dim">model</div>
              <div className="font-mono text-text">{debug?.model || "-"}</div>
            </div>
            <div>
              <div className="text-text-dim">tokens</div>
              <div className="font-mono text-text">
                {debug ? String(debug.tokens_used) : "-"}
              </div>
            </div>
            <div>
              <div className="text-text-dim">latency</div>
              <div className="font-mono text-text">{debug ? `${debug.ms} ms` : "-"}</div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
