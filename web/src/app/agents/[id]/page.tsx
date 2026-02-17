"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useToast } from "@/components/ToastProvider";
import { apiFetch, formatApiErrorRu } from "@/lib/api";
import {
  AgentDetailResponse,
  ConfigMigrateResponse,
  ConfigValidateRuntimeResponse,
} from "@/types/api";

type TabId = "main" | "rules" | "intents" | "channels";

type AgentStyle = {
  tone: string;
  politeness: string;
  emoji_policy: string;
  greeting: string;
  clean_text?: boolean;
  max_sentences: number;
  max_questions: number;
};

type AgentRule = {
  id: string;
  priority: string;
  description: string;
  positive_example?: string;
  negative_example?: string;
};

type LLMConfig = {
  provider: "openai" | "anthropic" | "google" | string;
  model: string;
  temperature: number;
  max_history?: number;
};

type ChannelConfig = {
  type: string;
  config: Record<string, unknown>;
};

type AgentConfigShape = {
  id?: string;
  name?: string;
  style?: Partial<AgentStyle>;
  rules?: AgentRule[];
  llm?: Partial<LLMConfig>;
  channels?: ChannelConfig[];
};

type IntentContract = {
  must_include_any?: string[];
  forbidden?: string[];
};

type IntentConfig = {
  id: string;
  markers: string[];
  priority?: number;
  contract?: IntentContract;
};

type DialoguePolicyShape = {
  intents?: IntentConfig[];
  conversation_flow?: Record<string, unknown>;
};

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v) => typeof v === "string") as string[];
}

function parseJsonObject(text: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  try {
    const v: unknown = JSON.parse(text);
    if (!v || typeof v !== "object" || Array.isArray(v)) {
      return { ok: false, error: "JSON должен быть объектом" };
    }
    return { ok: true, value: v as Record<string, unknown> };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Ошибка парсинга JSON" };
  }
}

function normalizeConfig(raw: Record<string, unknown>): Required<Pick<AgentConfigShape, "style" | "rules" | "llm" | "channels">> & AgentConfigShape {
  const styleRaw = asObject(raw.style);
  const llmRaw = asObject(raw.llm);
  const rulesRaw = Array.isArray(raw.rules) ? raw.rules : [];
  const channelsRaw = Array.isArray(raw.channels) ? raw.channels : [];

  const style: AgentStyle = {
    tone: asString(styleRaw.tone, "warm_professional"),
    politeness: asString(styleRaw.politeness, "вы"),
    emoji_policy: asString(styleRaw.emoji_policy, "rare"),
    greeting: asString(styleRaw.greeting, ""),
    clean_text: typeof styleRaw.clean_text === "boolean" ? styleRaw.clean_text : true,
    max_sentences: asNumber(styleRaw.max_sentences, 3),
    max_questions: asNumber(styleRaw.max_questions, 1),
  };

  const llm: LLMConfig = {
    provider: asString(llmRaw.provider, "openai"),
    model: asString(llmRaw.model, "gpt-4o"),
    temperature: asNumber(llmRaw.temperature, 0.3),
    max_history: typeof llmRaw.max_history === "number" ? llmRaw.max_history : undefined,
  };

  const rules: AgentRule[] = rulesRaw
    .map((r) => (typeof r === "object" && r && !Array.isArray(r) ? (r as Record<string, unknown>) : null))
    .filter((r): r is Record<string, unknown> => r !== null)
    .map((r) => ({
      id: asString(r.id),
      priority: asString(r.priority, "normal"),
      description: asString(r.description),
      positive_example: typeof r.positive_example === "string" ? r.positive_example : undefined,
      negative_example: typeof r.negative_example === "string" ? r.negative_example : undefined,
    }))
    .filter((r) => r.id.length > 0);

  const channels: ChannelConfig[] = channelsRaw
    .map((c) => (typeof c === "object" && c && !Array.isArray(c) ? (c as Record<string, unknown>) : null))
    .filter((c): c is Record<string, unknown> => c !== null)
    .map((c) => ({
      type: asString(c.type),
      config: asObject(c.config),
    }))
    .filter((c) => c.type.length > 0);

  return { ...raw, style, rules, llm, channels };
}

function normalizeDialoguePolicy(raw: Record<string, unknown>): Required<Pick<DialoguePolicyShape, "intents">> & DialoguePolicyShape {
  const intentsRaw = Array.isArray(raw.intents) ? raw.intents : [];
  const intents: IntentConfig[] = intentsRaw
    .map((i) => (typeof i === "object" && i && !Array.isArray(i) ? (i as Record<string, unknown>) : null))
    .filter((i): i is Record<string, unknown> => i !== null)
    .map((i) => ({
      id: asString(i.id),
      markers: asStringArray(i.markers),
      priority: typeof i.priority === "number" ? i.priority : undefined,
      contract: i.contract && typeof i.contract === "object" && !Array.isArray(i.contract) ? (i.contract as IntentContract) : undefined,
    }))
    .filter((i) => i.id.length > 0);

  return { ...raw, intents };
}

const TABS: { id: TabId; label: string }[] = [
  { id: "main", label: "Основные настройки" },
  { id: "rules", label: "Бизнес-правила" },
  { id: "intents", label: "Намерения клиентов" },
  { id: "channels", label: "Подключённые каналы" },
];

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();

  const agentId = params.id;

  const [tab, setTab] = useState<TabId>("main");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [agent, setAgent] = useState<AgentDetailResponse | null>(null);

  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [dialoguePolicy, setDialoguePolicy] = useState<Record<string, unknown>>({});

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const a = await apiFetch<AgentDetailResponse>(`/api/v1/agents/${agentId}`);
        setAgent(a);
        setConfig(normalizeConfig(a.config));
        setDialoguePolicy(normalizeDialoguePolicy(a.dialogue_policy));
      } catch (e) {
        toast.push({
          variant: "error",
          title: "Ошибка загрузки агента",
          message: formatApiErrorRu(e),
        });
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [agentId, toast]);

  const normalized = useMemo(() => normalizeConfig(config), [config]);
  const dp = useMemo(() => normalizeDialoguePolicy(dialoguePolicy), [dialoguePolicy]);

  async function save() {
    try {
      setSaving(true);

      // 1) Migrate config schema to latest before save.
      const migrated = await apiFetch<ConfigMigrateResponse>("/api/v1/agents/config/migrate", {
        method: "POST",
        body: JSON.stringify({ config }),
      });

      // 2) Validate + build runtime payload (no manual code path).
      const actionsRaw = asObject(agent.actions_config).actions;
      const actions = Array.isArray(actionsRaw)
        ? actionsRaw.filter((x) => typeof x === "object" && x && !Array.isArray(x))
        : [];

      const validation = await apiFetch<ConfigValidateRuntimeResponse>(
        "/api/v1/agents/config/validate-runtime",
        {
          method: "POST",
          body: JSON.stringify({
            config: migrated.migrated,
            dialogue_policy: dialoguePolicy,
            actions,
            tenant_slug: agent.slug,
          }),
        }
      );

      if (!validation.valid) {
        const msg = validation.errors?.length
          ? validation.errors.slice(0, 3).join("; ")
          : "Конфигурация не прошла валидацию";
        toast.push({
          variant: "error",
          title: "Ошибка валидации конфигурации",
          message: msg,
        });
        return;
      }

      // 3) Persist validated config.
      const updated = await apiFetch<AgentDetailResponse>(`/api/v1/agents/${agentId}`, {
        method: "PATCH",
        body: JSON.stringify({
          config: migrated.migrated,
          dialogue_policy: dialoguePolicy,
        }),
      });
      setAgent(updated);
      setConfig(normalizeConfig(updated.config));
      setDialoguePolicy(normalizeDialoguePolicy(updated.dialogue_policy));
      toast.push({
        variant: "success",
        title: "Сохранено",
        message: `Схема: ${validation.schema_version}`,
      });
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка сохранения",
        message: formatApiErrorRu(e),
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading || !agent) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-2/3 rounded bg-border animate-pulse" />
        <div className="h-32 rounded-xl border border-border bg-bg-card animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <button
            type="button"
            className="text-xs text-text-dim hover:text-text transition-colors"
            onClick={() => router.push("/agents")}
          >
            ← Назад к агентам
          </button>
          <h1 className="mt-1 truncate font-mono text-xl">{agent.name}</h1>
          <div className="mt-1 text-sm text-text-dim">
            Идентификатор: <span className="font-mono text-text-muted">{agent.slug}</span>
          </div>
          <div className="mt-1 text-xs text-text-dim">
            Версия схемы: <span className="font-mono text-text-muted">{asString(asObject(config).schema_version, "1.0.0")}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={save} disabled={saving}>
            Сохранить
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={[
              "rounded-lg border px-3 py-2 text-sm transition-colors",
              tab === t.id
                ? "border-border-light bg-bg-hover text-text"
                : "border-border text-text-muted hover:bg-bg-hover hover:text-text",
            ].join(" ")}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "main" ? (
        <Card className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Тон общения</div>
              <input
                value={normalized.style.tone}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: { ...asObject(p.style), tone: e.target.value },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                placeholder="дружелюбный / формальный"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Обращение</div>
              <input
                value={normalized.style.politeness}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: { ...asObject(p.style), politeness: e.target.value },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                placeholder="вы"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Использование эмодзи</div>
              <input
                value={normalized.style.emoji_policy}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: { ...asObject(p.style), emoji_policy: e.target.value },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                placeholder="никогда"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Приветствие</div>
              <input
                value={normalized.style.greeting}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: { ...asObject(p.style), greeting: e.target.value },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                placeholder="Здравствуйте! Чем могу помочь?"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Макс. предложений в ответе</div>
              <input
                type="number"
                value={normalized.style.max_sentences}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: {
                      ...asObject(p.style),
                      max_sentences: Number(e.target.value || 0),
                    },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-text-dim">Макс. вопросов в ответе</div>
              <input
                type="number"
                value={normalized.style.max_questions}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: {
                      ...asObject(p.style),
                      max_questions: Number(e.target.value || 0),
                    },
                  }))
                }
                className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
              />
            </div>
            <label className="flex items-center gap-3 md:col-span-2">
              <input
                type="checkbox"
                checked={Boolean(normalized.style.clean_text)}
                onChange={(e) =>
                  setConfig((p) => ({
                    ...p,
                    style: { ...asObject(p.style), clean_text: e.target.checked },
                  }))
                }
                className="h-4 w-4 accent-accent"
              />
              <span className="text-xs text-text-dim">Очищать форматирование</span>
            </label>
          </div>

          <div className="border-t border-border pt-6">
            <div className="mb-3 font-mono text-sm">Настройки ИИ</div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <div className="text-xs text-text-dim">Провайдер ИИ</div>
                <select
                  value={asString(asObject(normalized.llm).provider, "openai")}
                  onChange={(e) =>
                    setConfig((p) => ({
                      ...p,
                      llm: { ...asObject(p.llm), provider: e.target.value },
                    }))
                  }
                  className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                >
                  <option value="openai">openai</option>
                  <option value="anthropic">anthropic</option>
                  <option value="google">google</option>
                </select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <div className="text-xs text-text-dim">Модель</div>
                <input
                  value={asString(asObject(normalized.llm).model, "")}
                  onChange={(e) =>
                    setConfig((p) => ({
                      ...p,
                      llm: { ...asObject(p.llm), model: e.target.value },
                    }))
                  }
                  className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                  placeholder="gpt-4o"
                />
              </div>
              <div className="space-y-2 md:col-span-3">
                <div className="flex items-center justify-between text-xs text-text-dim">
                  <span>Температура (креативность)</span>
                  <span className="font-mono text-text-muted">
                    {asNumber(asObject(normalized.llm).temperature, 0.3).toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={asNumber(asObject(normalized.llm).temperature, 0.3)}
                  onChange={(e) =>
                    setConfig((p) => ({
                      ...p,
                      llm: { ...asObject(p.llm), temperature: Number(e.target.value) },
                    }))
                  }
                  className="w-full"
                />
              </div>
              <div className="space-y-2 md:col-span-3">
                <div className="text-xs text-text-dim">Глубина памяти (сообщений)</div>
                <input
                  type="number"
                  value={asNumber(asObject(normalized.llm).max_history, 20)}
                  onChange={(e) =>
                    setConfig((p) => ({
                      ...p,
                      llm: { ...asObject(p.llm), max_history: Number(e.target.value || 0) },
                    }))
                  }
                  className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                  placeholder="20"
                />
              </div>
            </div>
          </div>
        </Card>
      ) : null}

      {tab === "rules" ? (
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-sm">Бизнес-правила</div>
            <Button
              variant="primary"
              onClick={() =>
                setConfig((p) => ({
                  ...p,
                  rules: [
                    ...(Array.isArray(p.rules) ? (p.rules as AgentRule[]) : []),
                    {
                      id: `правило_${(Array.isArray(p.rules) ? (p.rules as AgentRule[]).length : 0) + 1}`,
                      priority: "normal",
                      description: "",
                    },
                  ],
                }))
              }
            >
              + Добавить правило
            </Button>
          </div>

          <div className="space-y-3">
            {normalized.rules.length === 0 ? (
              <div className="text-sm text-text-dim">Правила не добавлены.</div>
            ) : null}

            {normalized.rules.map((r, idx) => (
              <div key={`${r.id}-${idx}`} className="rounded-xl border border-border p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-1 flex-col gap-3 md:flex-row">
                    <div className="flex-1 space-y-1">
                      <div className="text-xs text-text-dim">Номер правила</div>
                      <input
                        value={r.id}
                        onChange={(e) =>
                          setConfig((p) => ({
                            ...p,
                            rules: normalized.rules.map((x, i) =>
                              i === idx ? { ...x, id: e.target.value } : x
                            ),
                          }))
                        }
                        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                        placeholder="правило_1"
                      />
                    </div>
                    <div className="w-full md:w-48 space-y-1">
                      <div className="text-xs text-text-dim">Приоритет</div>
                      <select
                        value={r.priority}
                        onChange={(e) =>
                          setConfig((p) => ({
                            ...p,
                            rules: normalized.rules.map((x, i) =>
                              i === idx ? { ...x, priority: e.target.value } : x
                            ),
                          }))
                        }
                        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                      >
                        {!["critical", "high", "normal", "low"].includes(r.priority) ? (
                          <option value={r.priority}>{r.priority}</option>
                        ) : null}
                        <option value="critical">Критический</option>
                        <option value="high">Высокий</option>
                        <option value="normal">Обычный</option>
                        <option value="low">Низкий</option>
                      </select>
                    </div>
                  </div>
                  <Button
                    variant="danger"
                    onClick={() =>
                      setConfig((p) => ({
                        ...p,
                        rules: normalized.rules.filter((_x, i) => i !== idx),
                      }))
                    }
                  >
                    Удалить
                  </Button>
                </div>

                <div className="mt-3 space-y-2">
                  <div className="text-xs text-text-dim">Описание</div>
                  <textarea
                    value={r.description}
                    onChange={(e) =>
                      setConfig((p) => ({
                        ...p,
                        rules: normalized.rules.map((x, i) =>
                          i === idx ? { ...x, description: e.target.value } : x
                        ),
                      }))
                    }
                    rows={3}
                    className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                  />
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <div className="text-xs text-text-dim">Пример правильного ответа</div>
                    <textarea
                      value={r.positive_example || ""}
                      onChange={(e) =>
                        setConfig((p) => ({
                          ...p,
                          rules: normalized.rules.map((x, i) =>
                            i === idx ? { ...x, positive_example: e.target.value } : x
                          ),
                        }))
                      }
                      rows={2}
                      className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                    />
                  </div>
                  <div className="space-y-2">
                    <div className="text-xs text-text-dim">Пример неправильного ответа</div>
                    <textarea
                      value={r.negative_example || ""}
                      onChange={(e) =>
                        setConfig((p) => ({
                          ...p,
                          rules: normalized.rules.map((x, i) =>
                            i === idx ? { ...x, negative_example: e.target.value } : x
                          ),
                        }))
                      }
                      rows={2}
                      className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {tab === "intents" ? (
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-sm">Намерения клиентов</div>
            <Button
              variant="primary"
              onClick={() =>
                setDialoguePolicy((p) => ({
                  ...p,
                  intents: [
                    ...(Array.isArray(p.intents) ? (p.intents as IntentConfig[]) : []),
                    {
                      id: `намерение_${(Array.isArray(p.intents) ? (p.intents as IntentConfig[]).length : 0) + 1}`,
                      markers: [],
                      priority: 50,
                      contract: { must_include_any: [], forbidden: [] },
                    },
                  ],
                }))
              }
            >
              + Добавить намерение
            </Button>
          </div>

          <div className="space-y-3">
            {dp.intents.length === 0 ? (
              <div className="text-sm text-text-dim">Намерения не добавлены.</div>
            ) : null}

            {dp.intents.map((intent, idx) => (
              <div key={`${intent.id}-${idx}`} className="rounded-xl border border-border p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="flex flex-1 flex-col gap-3 md:flex-row">
                    <div className="flex-1 space-y-1">
                      <div className="text-xs text-text-dim">Код намерения</div>
                      <input
                        value={intent.id}
                        onChange={(e) =>
                          setDialoguePolicy((p) => ({
                            ...p,
                            intents: dp.intents.map((x, i) => (i === idx ? { ...x, id: e.target.value } : x)),
                          }))
                        }
                        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                        placeholder="намерение_1"
                      />
                    </div>
                    <div className="w-full md:w-40 space-y-1">
                      <div className="text-xs text-text-dim">Приоритет</div>
                      <input
                        type="number"
                        value={intent.priority ?? 50}
                        onChange={(e) =>
                          setDialoguePolicy((p) => ({
                            ...p,
                            intents: dp.intents.map((x, i) =>
                              i === idx ? { ...x, priority: Number(e.target.value || 0) } : x
                            ),
                          }))
                        }
                        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                      />
                    </div>
                  </div>
                  <Button
                    variant="danger"
                    onClick={() =>
                      setDialoguePolicy((p) => ({
                        ...p,
                        intents: dp.intents.filter((_x, i) => i !== idx),
                      }))
                    }
                  >
                    Удалить
                  </Button>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <div className="text-xs text-text-dim">Ключевые слова</div>
                    <div className="text-[11px] text-text-dim">
                      Ключевые слова через запятую, по которым определяется намерение клиента
                    </div>
                    <input
                      value={intent.markers.join(", ")}
                      onChange={(e) =>
                        setDialoguePolicy((p) => ({
                          ...p,
                          intents: dp.intents.map((x, i) =>
                            i === idx
                              ? { ...x, markers: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) }
                              : x
                          ),
                        }))
                      }
                      className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                      placeholder="цена, стоимость, прайс"
                    />
                  </div>
                  <div className="md:col-span-2 pt-2 text-xs text-text-dim font-mono">Контракт ответа</div>
                  <div className="space-y-2 md:col-span-2">
                    <div className="text-xs text-text-dim">Обязательные слова (хотя бы одно)</div>
                    <input
                      value={(intent.contract?.must_include_any || []).join(", ")}
                      onChange={(e) =>
                        setDialoguePolicy((p) => ({
                          ...p,
                          intents: dp.intents.map((x, i) => {
                            if (i !== idx) return x;
                            const must = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                            return { ...x, contract: { ...(x.contract || {}), must_include_any: must } };
                          }),
                        }))
                      }
                      className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                      placeholder="руб, ₽"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <div className="text-xs text-text-dim">Запрещённые слова</div>
                    <input
                      value={(intent.contract?.forbidden || []).join(", ")}
                      onChange={(e) =>
                        setDialoguePolicy((p) => ({
                          ...p,
                          intents: dp.intents.map((x, i) => {
                            if (i !== idx) return x;
                            const forbidden = e.target.value
                              .split(",")
                              .map((s) => s.trim())
                              .filter(Boolean);
                            return { ...x, contract: { ...(x.contract || {}), forbidden } };
                          }),
                        }))
                      }
                      className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                      placeholder="не знаю"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {tab === "channels" ? (
        <ChannelsTab
          channels={normalized.channels}
          onChange={(next) => setConfig((p) => ({ ...p, channels: next }))}
        />
      ) : null}
    </div>
  );
}

function ChannelsTab({
  channels,
  onChange,
}: {
  channels: ChannelConfig[];
  onChange: (channels: ChannelConfig[]) => void;
}) {
  const toast = useToast();
  const [newType, setNewType] = useState("umnico");
  const [newToken, setNewToken] = useState("");
  const [newWebhookUrl, setNewWebhookUrl] = useState("");

  function channelTypeLabel(type: string): string {
    if (type === "umnico") return "Umnico (мессенджеры)";
    if (type === "telegram") return "Telegram-бот";
    return type;
  }

  return (
    <Card className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="font-mono text-sm">Подключённые каналы</div>
          <div className="mt-1 text-xs text-text-dim">
            Здесь настраиваются каналы, через которые агент получает и отправляет сообщения.
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {channels.length === 0 ? (
          <div className="text-sm text-text-dim">Нет каналов.</div>
        ) : null}

        {channels.map((ch, idx) => (
          <div key={`${ch.type}-${idx}`} className="rounded-xl border border-border p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <div className="text-xs text-text-dim">Тип канала</div>
                <div className="mt-1 truncate font-mono text-sm">{channelTypeLabel(ch.type)}</div>
              </div>
              <Button variant="danger" onClick={() => onChange(channels.filter((_c, i) => i !== idx))}>
                Удалить
              </Button>
            </div>

            <div className="mt-4 text-xs text-text-dim font-mono">Настройки</div>
            <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <div className="text-xs text-text-dim">Токен</div>
                <input
                  type="password"
                  value={asString(asObject(ch.config).token, "")}
                  onChange={(e) => {
                    const next = channels.map((x, i) => {
                      if (i !== idx) return x;
                      return { ...x, config: { ...asObject(x.config), token: e.target.value } };
                    });
                    onChange(next);
                  }}
                  className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                  placeholder="(необязательно)"
                />
                <div className="text-[11px] text-text-dim">
                  Токены лучше хранить в разделе «Секреты».
                </div>
              </div>
              <div className="space-y-2">
                <div className="text-xs text-text-dim">URL для входящих сообщений</div>
                <input
                  value={asString(asObject(ch.config).webhook_url, "")}
                  onChange={(e) => {
                    const next = channels.map((x, i) => {
                      if (i !== idx) return x;
                      return { ...x, config: { ...asObject(x.config), webhook_url: e.target.value } };
                    });
                    onChange(next);
                  }}
                  className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
                  placeholder="https://ваш-домен/api/v1/webhooks/..."
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-border p-4">
        <div className="font-mono text-sm">Добавить канал</div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <div className="text-xs text-text-dim">Тип канала</div>
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
            >
              <option value="umnico">Umnico (мессенджеры)</option>
              <option value="telegram">Telegram-бот</option>
            </select>
          </div>
          <div className="space-y-2">
            <div className="text-xs text-text-dim">Токен</div>
            <input
              type="password"
              value={newToken}
              onChange={(e) => setNewToken(e.target.value)}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
              placeholder="(необязательно)"
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <div className="text-xs text-text-dim">URL для входящих сообщений</div>
            <input
              value={newWebhookUrl}
              onChange={(e) => setNewWebhookUrl(e.target.value)}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
              placeholder="https://ваш-домен/api/v1/webhooks/..."
            />
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <Button
            variant="primary"
            onClick={() => {
              const token = newToken.trim();
              const webhook_url = newWebhookUrl.trim();
              const cfg: Record<string, unknown> = {};
              if (token) cfg.token = token;
              if (webhook_url) cfg.webhook_url = webhook_url;

              onChange([...channels, { type: newType, config: cfg }]);
              setNewToken("");
              setNewWebhookUrl("");
              toast.push({ variant: "success", title: "Канал добавлен", message: channelTypeLabel(newType) });
            }}
          >
            Добавить канал
          </Button>
        </div>
      </div>
    </Card>
  );
}
