"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/ToastProvider";
import { apiFetch, formatApiErrorRu } from "@/lib/api";
import { AgentResponse } from "@/types/api";

type CreateAgentForm = {
  tenant_slug: string;
  agent_slug: string;
  name: string;
};

function shortId(id: string): string {
  if (id.length <= 12) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

export default function AgentsPage() {
  const router = useRouter();
  const toast = useToast();

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [tenantSuggestions, setTenantSuggestions] = useState<string[]>([]);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateAgentForm>({
    tenant_slug: "",
    agent_slug: "",
    name: "",
  });

  const activeCount = useMemo(() => agents.filter((a) => a.is_active).length, [agents]);

  async function loadAgents() {
    try {
      setLoading(true);
      const list = await apiFetch<AgentResponse[]>("/api/v1/agents");
      setAgents(list);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки агентов",
        message: formatApiErrorRu(e),
      });
    } finally {
      setLoading(false);
    }
  }

  async function loadTenantSuggestions() {
    try {
      const slugs = await apiFetch<string[]>("/api/v1/tenants/discover");
      setTenantSuggestions(slugs);
      if (!createForm.tenant_slug && slugs.length > 0) {
        setCreateForm((p) => ({ ...p, tenant_slug: slugs[0] }));
      }
    } catch {
      // Optional UX improvement; ignore errors to avoid noisy toasts.
    }
  }

  useEffect(() => {
    void loadAgents();
    void loadTenantSuggestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggleAgent(agent: AgentResponse) {
    try {
      setBusyId(agent.id);
      const updated = await apiFetch<AgentResponse>(`/api/v1/agents/${agent.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !agent.is_active }),
      });
      setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка изменения статуса",
        message: formatApiErrorRu(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  async function syncAgent(agent: AgentResponse) {
    try {
      setBusyId(agent.id);
      const updated = await apiFetch<AgentResponse>(`/api/v1/agents/${agent.id}/sync`, {
        method: "POST",
      });
      setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      toast.push({ variant: "success", title: "Синхронизировано", message: agent.slug });
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка синхронизации",
        message: formatApiErrorRu(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  async function createAgent() {
    const payload = {
      tenant_slug: createForm.tenant_slug.trim(),
      agent_slug: createForm.agent_slug.trim(),
      name: createForm.name.trim() || undefined,
    };

    if (!payload.tenant_slug || !payload.agent_slug) {
      toast.push({ variant: "info", title: "Заполните тенант и слаг" });
      return;
    }

    try {
      setBusyId("create");
      const created = await apiFetch<AgentResponse>("/api/v1/agents", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCreateOpen(false);
      setCreateForm({ tenant_slug: "", agent_slug: "", name: "" });
      setAgents((prev) => [created, ...prev]);
      toast.push({ variant: "success", title: "Агент создан", message: created.slug });
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка создания агента",
        message: formatApiErrorRu(e),
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">Агенты</h1>
          <div className="mt-1 text-sm text-text-dim">
            Всего: {agents.length} | Активных: {activeCount}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={loadAgents} disabled={loading}>
            Обновить
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            + Новый агент
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="rounded-xl border border-border bg-bg-card p-4 animate-pulse"
            >
              <div className="h-4 w-1/2 rounded bg-border" />
              <div className="mt-3 h-3 w-2/3 rounded bg-border" />
              <div className="mt-4 h-8 w-full rounded bg-border" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {agents.map((a) => (
            <Card
              key={a.id}
              className="cursor-pointer hover:bg-bg-hover transition-colors"
              onClick={() => router.push(`/agents/${a.id}`)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className={[
                        "inline-block h-2.5 w-2.5 rounded-full",
                        a.is_active ? "bg-accent" : "bg-border-light",
                      ].join(" ")}
                    />
                    <div className="truncate font-mono text-sm">{a.name}</div>
                  </div>
                  <div className="mt-1 text-xs text-text-dim">
                    слаг: <span className="font-mono text-text-muted">{a.slug}</span>
                  </div>
                  <div className="mt-1 text-xs text-text-dim">
                    тенант: <span className="font-mono text-text-muted">{shortId(a.tenant_id)}</span>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    variant={a.is_active ? "secondary" : "primary"}
                    disabled={busyId === a.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      void toggleAgent(a);
                    }}
                  >
                    {a.is_active ? "⏹ Стоп" : "⚡ Старт"}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busyId === a.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      void syncAgent(a);
                    }}
                  >
                    🔄 Синхронизировать
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal title="Новый агент" open={createOpen} onClose={() => setCreateOpen(false)}>
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="block text-xs text-text-dim">Тенант (slug)</label>
            <input
              value={createForm.tenant_slug}
              onChange={(e) => setCreateForm((p) => ({ ...p, tenant_slug: e.target.value }))}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-border-light"
              placeholder="j-one-studio"
            />
            <div className="text-xs text-text-dim">
              Если tenant отсутствует в БД, он будет создан автоматически при создании агента.
            </div>
            {tenantSuggestions.length > 0 ? (
              <div className="flex flex-wrap gap-2 pt-1">
                {tenantSuggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setCreateForm((p) => ({ ...p, tenant_slug: s }))}
                    className="rounded-lg border border-border bg-bg px-2 py-1 text-xs text-text-dim hover:bg-bg-hover transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="space-y-2">
            <label className="block text-xs text-text-dim">Агент (slug)</label>
            <input
              value={createForm.agent_slug}
              onChange={(e) => setCreateForm((p) => ({ ...p, agent_slug: e.target.value }))}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-border-light"
              placeholder="j-one-sales"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-xs text-text-dim">Имя</label>
            <input
              value={createForm.name}
              onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none focus:border-border-light"
              placeholder="Менеджер"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={busyId === "create"}>
              Отмена
            </Button>
            <Button variant="primary" onClick={createAgent} disabled={busyId === "create"}>
              Создать
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
