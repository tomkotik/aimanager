"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/ToastProvider";
import { apiFetch, formatApiErrorRu } from "@/lib/api";
import { AgentResponse, ReliabilityOverviewResponse } from "@/types/api";

type WindowHours = 1 | 6 | 24 | 168 | 720;

const WINDOWS: { value: WindowHours; label: string }[] = [
  { value: 1, label: "1 час" },
  { value: 6, label: "6 часов" },
  { value: 24, label: "24 часа" },
  { value: 168, label: "7 дней" },
  { value: 720, label: "30 дней" },
];

function formatPct(v: number | null): string {
  if (v === null) return "—";
  return `${v.toFixed(1)}%`;
}

function formatMs(v: number | null): string {
  if (v === null) return "—";
  if (v < 1000) return `${Math.round(v)} мс`;
  return `${(v / 1000).toFixed(2)} с`;
}

function sloColor(value: number | null, target: number, good: "above" | "below"): string {
  if (value === null) return "text-text-dim";
  const ok = good === "above" ? value >= target : value <= target;
  return ok ? "text-accent" : "text-danger";
}

function SloKpi({
  title,
  value,
  target,
  loading,
  color,
}: {
  title: string;
  value: string;
  target?: string;
  loading: boolean;
  color?: string;
}) {
  return (
    <Card>
      <div className="text-xs text-text-dim">{title}</div>
      {loading ? (
        <div className="mt-3 h-7 w-2/3 rounded bg-border/40 animate-pulse" />
      ) : (
        <>
          <div className={`mt-2 font-mono text-2xl ${color || ""}`}>{value}</div>
          {target ? (
            <div className="mt-1 text-[11px] text-text-dim">Цель: {target}</div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function StatusBreakdown({
  data,
  loading,
}: {
  data: ReliabilityOverviewResponse | null;
  loading: boolean;
}) {
  if (loading || !data) {
    return <div className="h-48 rounded-lg bg-border/40 animate-pulse" />;
  }

  const statuses = [
    {
      label: "✅ Создано (booking)",
      count: data.created_count,
      color: "bg-accent",
    },
    {
      label: "🔴 Занято",
      count: data.busy_count,
      color: "bg-[#F59E0B]",
    },
    {
      label: "🔴 Занято → эскалация",
      count: data.busy_escalated_count,
      color: "bg-danger",
    },
    {
      label: "⏳ Ожидает менеджера",
      count: data.pending_manager_count,
      color: "bg-[#60A5FA]",
    },
  ];

  const total =
    data.created_count +
    data.busy_count +
    data.busy_escalated_count +
    data.pending_manager_count;

  return (
    <div className="space-y-3">
      {statuses.map((s) => {
        const pct = total > 0 ? (s.count / total) * 100 : 0;
        return (
          <div key={s.label}>
            <div className="flex items-center justify-between text-sm">
              <span>{s.label}</span>
              <span className="font-mono text-text-muted">
                {s.count} ({pct.toFixed(1)}%)
              </span>
            </div>
            <div className="mt-1 h-2 w-full rounded-full bg-border">
              <div
                className={`h-2 rounded-full ${s.color} transition-all`}
                style={{ width: `${Math.max(pct, 0.5)}%` }}
              />
            </div>
          </div>
        );
      })}
      <div className="flex items-center justify-between border-t border-border pt-2 text-xs text-text-dim">
        <span>Финализировано диалогов</span>
        <span className="font-mono">{data.finalized_conversations}</span>
      </div>
    </div>
  );
}

function IncidentPanel({
  data,
  loading,
}: {
  data: ReliabilityOverviewResponse | null;
  loading: boolean;
}) {
  if (loading || !data) {
    return <div className="h-24 rounded-lg bg-border/40 animate-pulse" />;
  }

  const incidents = [
    {
      label: "Ложные подтверждения бронирования",
      count: data.false_confirmation_count,
      danger: data.false_confirmation_count > 0,
    },
    {
      label: "Критические инциденты (contract violations)",
      count: data.critical_incident_count,
      danger: data.critical_incident_count > 0,
    },
  ];

  return (
    <div className="space-y-3">
      {incidents.map((item) => (
        <div
          key={item.label}
          className={`flex items-center justify-between rounded-lg border px-3 py-2 ${
            item.danger
              ? "border-danger/50 bg-danger/10"
              : "border-border bg-bg"
          }`}
        >
          <span className="text-sm">{item.label}</span>
          <span
            className={`font-mono text-lg ${
              item.danger ? "text-danger" : "text-accent"
            }`}
          >
            {item.count}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ReliabilityPage() {
  const toast = useToast();

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [agentId, setAgentId] = useState<string>("");
  const [hours, setHours] = useState<WindowHours>(24);

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ReliabilityOverviewResponse | null>(null);

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

  async function loadReliability() {
    if (!agentId) return;
    try {
      setLoading(true);
      const params = new URLSearchParams({
        agent_id: agentId,
        hours: String(hours),
      });
      const res = await apiFetch<ReliabilityOverviewResponse>(
        `/api/v1/analytics/reliability?${params.toString()}`
      );
      setData(res);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки SLO",
        message: formatApiErrorRu(e),
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!agentId) return;
    void loadReliability();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, hours]);

  // Auto-refresh every 60 seconds.
  useEffect(() => {
    if (!agentId) return;
    const id = window.setInterval(() => void loadReliability(), 60_000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, hours]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">🛡️ SLO / Надёжность</h1>
          <div className="mt-1 text-sm text-text-dim">
            Метрики качества бронирований, точности детекции и инцидентов
          </div>
        </div>
      </div>

      {/* Filters */}
      <Card className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
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

        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="text-xs text-text-dim">Окно</div>
          <select
            value={String(hours)}
            onChange={(e) => setHours(Number(e.target.value) as WindowHours)}
            className="w-full md:w-48 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
          >
            {WINDOWS.map((w) => (
              <option key={w.value} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            onClick={() => void loadReliability()}
            disabled={loading}
          >
            Обновить
          </Button>
        </div>
      </Card>

      {/* KPI Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SloKpi
          title="📈 Успешность бронирований"
          value={formatPct(data?.booking_success_rate_pct ?? null)}
          target="≥ 85%"
          loading={loading}
          color={sloColor(
            data?.booking_success_rate_pct ?? null,
            85,
            "above"
          )}
        />
        <SloKpi
          title="🎯 Точность детекции «занято»"
          value={formatPct(data?.busy_detection_precision_pct ?? null)}
          target="≥ 95%"
          loading={loading}
          color={sloColor(
            data?.busy_detection_precision_pct ?? null,
            95,
            "above"
          )}
        />
        <SloKpi
          title="⚡ P95 Latency"
          value={formatMs(data?.p95_latency_ms ?? null)}
          target="≤ 3 000 мс"
          loading={loading}
          color={sloColor(data?.p95_latency_ms ?? null, 3000, "below")}
        />
        <SloKpi
          title="🚫 Ложных подтверждений"
          value={String(data?.false_confirmation_count ?? "—")}
          target="0"
          loading={loading}
          color={
            data
              ? data.false_confirmation_count === 0
                ? "text-accent"
                : "text-danger"
              : ""
          }
        />
      </div>

      {/* Detail panels */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <div className="mb-4 font-mono text-sm">Статусы бронирований</div>
          <StatusBreakdown data={data} loading={loading} />
        </Card>

        <Card>
          <div className="mb-4 font-mono text-sm">Инциденты</div>
          <IncidentPanel data={data} loading={loading} />

          {data && !loading ? (
            <div className="mt-6 space-y-2">
              <div className="text-xs text-text-dim font-mono">Сводка</div>
              <div className="rounded-lg border border-border bg-bg p-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-text-dim">Окно</span>
                  <span className="font-mono">{data.window_hours} ч</span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-text-dim">Финализировано</span>
                  <span className="font-mono">
                    {data.finalized_conversations}
                  </span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-text-dim">Всего статусов</span>
                  <span className="font-mono">
                    {data.created_count +
                      data.busy_count +
                      data.busy_escalated_count +
                      data.pending_manager_count}
                  </span>
                </div>
              </div>
            </div>
          ) : null}
        </Card>
      </div>
    </div>
  );
}
