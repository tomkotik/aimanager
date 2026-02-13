"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/ToastProvider";
import { apiFetch } from "@/lib/api";
import { AgentResponse, AnalyticsOverviewResponse } from "@/types/api";

type Period = 7 | 30 | 0;

const CHANNEL_COLORS = ["#10B981", "#F59E0B", "#3F3F46", "#EF4444", "#60A5FA"];

function formatNumber(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

export default function AnalyticsPage() {
  const toast = useToast();

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [agentId, setAgentId] = useState<string>("");
  const [days, setDays] = useState<Period>(7);

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<AnalyticsOverviewResponse | null>(null);

  async function loadAgents() {
    try {
      const list = await apiFetch<AgentResponse[]>("/api/v1/agents");
      setAgents(list);
      if (!agentId && list.length > 0) setAgentId(list[0].id);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки агентов",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    }
  }

  async function loadOverview() {
    if (!agentId) return;
    try {
      setLoading(true);
      const res = await apiFetch<AnalyticsOverviewResponse>(
        `/api/v1/analytics/overview?agent_id=${agentId}&days=${days}`
      );
      setData(res);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки аналитики",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
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
    void loadOverview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, days]);

  const kpi = useMemo(() => {
    if (!data) {
      return {
        totalConversations: 0,
        totalMessages: 0,
        avg: 0,
        todayConversations: 0,
      };
    }
    return {
      totalConversations: data.total_conversations,
      totalMessages: data.total_messages,
      avg: data.avg_messages_per_conversation,
      todayConversations: data.conversations_today,
    };
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">Аналитика</h1>
          <div className="mt-1 text-sm text-text-dim">Ключевые метрики по диалогам и сообщениям</div>
        </div>
      </div>

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
          <div className="text-xs text-text-dim">Период</div>
          <select
            value={String(days)}
            onChange={(e) => setDays(Number(e.target.value) as Period)}
            className="w-full md:w-56 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
          >
            <option value="7">7 дней</option>
            <option value="30">30 дней</option>
            <option value="0">всё время</option>
          </select>
          <Button variant="secondary" onClick={() => void loadOverview()} disabled={loading}>
            Обновить
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <KpiCard title="💬 Всего диалогов" value={formatNumber(kpi.totalConversations)} loading={loading} />
        <KpiCard title="📩 Всего сообщений" value={formatNumber(kpi.totalMessages)} loading={loading} />
        <KpiCard
          title="📈 Ср. сообщений/диалог"
          value={kpi.avg.toFixed(2)}
          loading={loading}
        />
        <KpiCard title="🕐 Диалогов сегодня" value={formatNumber(kpi.todayConversations)} loading={loading} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-7">
          <div className="font-mono text-sm">Сообщения по дням</div>
          <div className="mt-3 h-[320px]">
            {loading || !data ? (
              <div className="h-full rounded-lg bg-border/40 animate-pulse" />
            ) : data.messages_by_day.length === 0 ? (
              <div className="text-sm text-text-dim">Нет данных.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.messages_by_day}>
                  <XAxis dataKey="date" stroke="#71717A" fontSize={12} />
                  <YAxis stroke="#71717A" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      background: "#141416",
                      border: "1px solid #27272A",
                      borderRadius: 12,
                      color: "#FAFAFA",
                    }}
                  />
                  <Bar dataKey="user" fill="#3F3F46" name="user" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="assistant" fill="#10B981" name="assistant" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card className="lg:col-span-5">
          <div className="font-mono text-sm">Топ интентов</div>
          <div className="mt-3 h-[320px]">
            {loading || !data ? (
              <div className="h-full rounded-lg bg-border/40 animate-pulse" />
            ) : data.top_intents.length === 0 ? (
              <div className="text-sm text-text-dim">Нет данных.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[...data.top_intents].reverse()}
                  layout="vertical"
                  margin={{ left: 20, right: 20 }}
                >
                  <XAxis type="number" stroke="#71717A" fontSize={12} />
                  <YAxis type="category" dataKey="intent" stroke="#71717A" fontSize={12} width={90} />
                  <Tooltip
                    contentStyle={{
                      background: "#141416",
                      border: "1px solid #27272A",
                      borderRadius: 12,
                      color: "#FAFAFA",
                    }}
                  />
                  <Bar dataKey="count" fill="#F59E0B" radius={[6, 6, 6, 6]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <div className="font-mono text-sm">По каналам</div>
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="h-[260px]">
            {loading || !data ? (
              <div className="h-full rounded-lg bg-border/40 animate-pulse" />
            ) : data.conversations_by_channel.length === 0 ? (
              <div className="text-sm text-text-dim">Нет данных.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Tooltip
                    contentStyle={{
                      background: "#141416",
                      border: "1px solid #27272A",
                      borderRadius: 12,
                      color: "#FAFAFA",
                    }}
                  />
                  <Pie
                    data={data.conversations_by_channel}
                    dataKey="count"
                    nameKey="channel"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={2}
                  >
                    {data.conversations_by_channel.map((_entry, idx) => (
                      <Cell key={idx} fill={CHANNEL_COLORS[idx % CHANNEL_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="space-y-2">
            {loading || !data ? (
              <div className="h-32 rounded-lg bg-border/40 animate-pulse" />
            ) : (
              data.conversations_by_channel.map((c, idx) => (
                <div key={c.channel} className="flex items-center justify-between rounded-lg border border-border bg-bg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: CHANNEL_COLORS[idx % CHANNEL_COLORS.length] }}
                    />
                    <div className="font-mono text-sm">{c.channel}</div>
                  </div>
                  <div className="text-sm text-text-muted">{formatNumber(c.count)}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}

function KpiCard({ title, value, loading }: { title: string; value: string; loading: boolean }) {
  return (
    <Card>
      <div className="text-xs text-text-dim">{title}</div>
      {loading ? (
        <div className="mt-3 h-7 w-2/3 rounded bg-border/40 animate-pulse" />
      ) : (
        <div className="mt-2 font-mono text-2xl">{value}</div>
      )}
    </Card>
  );
}
