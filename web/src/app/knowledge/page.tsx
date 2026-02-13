"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { MarkdownPreview } from "@/components/MarkdownPreview";
import { Modal } from "@/components/Modal";
import { useToast } from "@/components/ToastProvider";
import { apiFetch } from "@/lib/api";
import { AgentResponse, KnowledgeFileInfo, KnowledgeFileResponse } from "@/types/api";

type CreateFileForm = {
  name: string;
  content: string;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

export default function KnowledgePage() {
  const toast = useToast();

  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [agentId, setAgentId] = useState<string>("");

  const [files, setFiles] = useState<KnowledgeFileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [preview, setPreview] = useState<boolean>(true);

  const [loadingAgents, setLoadingAgents] = useState(true);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingFile, setLoadingFile] = useState(false);
  const [saving, setSaving] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFileForm>({ name: "", content: "" });

  const selectedAgent = useMemo(
    () => agents.find((a) => a.id === agentId) || null,
    [agents, agentId]
  );

  async function loadAgents() {
    try {
      setLoadingAgents(true);
      const list = await apiFetch<AgentResponse[]>("/api/v1/agents");
      setAgents(list);
      if (!agentId && list.length > 0) setAgentId(list[0].id);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки агентов",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setLoadingAgents(false);
    }
  }

  async function loadFiles(nextAgentId: string) {
    if (!nextAgentId) return;
    try {
      setLoadingFiles(true);
      const list = await apiFetch<KnowledgeFileInfo[]>(`/api/v1/agents/${nextAgentId}/knowledge`);
      setFiles(list);
      setSelectedFile("");
      setContent("");
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки файлов",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setLoadingFiles(false);
    }
  }

  async function openFile(filename: string) {
    if (!agentId) return;
    try {
      setLoadingFile(true);
      const res = await apiFetch<KnowledgeFileResponse>(
        `/api/v1/agents/${agentId}/knowledge/${encodeURIComponent(filename)}`
      );
      setSelectedFile(res.name);
      setContent(res.content);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка загрузки файла",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setLoadingFile(false);
    }
  }

  async function saveFile() {
    if (!agentId || !selectedFile) return;
    try {
      setSaving(true);
      await apiFetch<KnowledgeFileResponse>(
        `/api/v1/agents/${agentId}/knowledge/${encodeURIComponent(selectedFile)}`,
        {
          method: "PUT",
          body: JSON.stringify({ content }),
        }
      );
      toast.push({ variant: "success", title: "Сохранено", message: selectedFile });
      await loadFiles(agentId);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка сохранения",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setSaving(false);
    }
  }

  async function deleteFile() {
    if (!agentId || !selectedFile) return;
    const ok = window.confirm(`Удалить файл ${selectedFile}?`);
    if (!ok) return;

    try {
      setSaving(true);
      await apiFetch<{ ok: true }>(
        `/api/v1/agents/${agentId}/knowledge/${encodeURIComponent(selectedFile)}`,
        { method: "DELETE" }
      );
      toast.push({ variant: "success", title: "Удалено", message: selectedFile });
      setSelectedFile("");
      setContent("");
      await loadFiles(agentId);
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка удаления",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setSaving(false);
    }
  }

  async function createFile() {
    if (!agentId) return;
    const name = createForm.name.trim();
    if (!name) {
      toast.push({ variant: "info", title: "Укажите имя файла (например pricing.md)" });
      return;
    }
    try {
      setSaving(true);
      await apiFetch<KnowledgeFileResponse>(`/api/v1/agents/${agentId}/knowledge`, {
        method: "POST",
        body: JSON.stringify({ name, content: createForm.content }),
      });
      setCreateOpen(false);
      setCreateForm({ name: "", content: "" });
      await loadFiles(agentId);
      await openFile(name);
      toast.push({ variant: "success", title: "Файл создан", message: name });
    } catch (e) {
      toast.push({
        variant: "error",
        title: "Ошибка создания файла",
        message: e instanceof Error ? e.message : "Неизвестная ошибка",
      });
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    void loadAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!agentId) return;
    void loadFiles(agentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="font-mono text-xl">База знаний</h1>
          <div className="mt-1 text-sm text-text-dim">
            Редактирование markdown-файлов KB для выбранного агента
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => void loadAgents()} disabled={loadingAgents}>
            Обновить
          </Button>
        </div>
      </div>

      <Card className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="text-sm text-text-muted">
          Агент:{" "}
          <span className="font-mono text-text">
            {selectedAgent ? selectedAgent.name : "не выбран"}
          </span>
        </div>
        <select
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          disabled={loadingAgents}
          className="w-full md:w-[420px] rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
        >
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.slug})
            </option>
          ))}
        </select>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <Card className="lg:col-span-4">
          <div className="flex items-center justify-between">
            <div className="font-mono text-sm">Файлы</div>
            <Button variant="primary" onClick={() => setCreateOpen(true)} disabled={!agentId}>
              + Новый файл
            </Button>
          </div>

          <div className="mt-3 space-y-1">
            {loadingFiles ? (
              <div className="space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="h-10 rounded-lg bg-border/40 animate-pulse" />
                ))}
              </div>
            ) : files.length === 0 ? (
              <div className="mt-3 text-sm text-text-dim">Нет файлов в knowledge/.</div>
            ) : (
              files.map((f) => (
                <button
                  key={f.name}
                  type="button"
                  onClick={() => void openFile(f.name)}
                  className={[
                    "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                    f.name === selectedFile
                      ? "border-border-light bg-bg-hover"
                      : "border-border hover:bg-bg-hover",
                  ].join(" ")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate font-mono text-sm">{f.name}</div>
                    <div className="text-xs text-text-dim">{formatBytes(f.size)}</div>
                  </div>
                  <div className="mt-1 text-xs text-text-dim">
                    {new Date(f.updated_at).toLocaleString()}
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card className="lg:col-span-8">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="font-mono text-sm">Редактор</div>
              <div className="mt-1 text-xs text-text-dim truncate">
                {selectedFile ? selectedFile : "Файл не выбран"}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="ghost"
                onClick={() => setPreview((p) => !p)}
                disabled={!selectedFile}
              >
                {preview ? "Скрыть превью" : "Показать превью"}
              </Button>
              <Button variant="secondary" onClick={() => void saveFile()} disabled={!selectedFile || saving}>
                Сохранить
              </Button>
              <Button variant="danger" onClick={() => void deleteFile()} disabled={!selectedFile || saving}>
                Удалить
              </Button>
            </div>
          </div>

          {loadingFile ? (
            <div className="mt-4 h-64 rounded-lg bg-border/40 animate-pulse" />
          ) : (
            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                disabled={!selectedFile}
                rows={18}
                className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm font-mono outline-none focus:border-border-light disabled:opacity-50"
                placeholder="Выберите файл слева или создайте новый..."
              />

              {preview ? (
                <div className="rounded-lg border border-border bg-bg p-3 overflow-auto max-h-[520px]">
                  <MarkdownPreview content={content} />
                </div>
              ) : (
                <div className="rounded-lg border border-border bg-bg p-3 text-sm text-text-dim">
                  Превью выключено.
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      <Modal title="Новый файл KB" open={createOpen} onClose={() => setCreateOpen(false)}>
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="text-xs text-text-dim">Имя файла</div>
            <input
              value={createForm.name}
              onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value }))}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-border-light"
              placeholder="pricing.md"
            />
          </div>
          <div className="space-y-2">
            <div className="text-xs text-text-dim">Контент</div>
            <textarea
              value={createForm.content}
              onChange={(e) => setCreateForm((p) => ({ ...p, content: e.target.value }))}
              rows={10}
              className="w-full resize-none rounded-lg border border-border bg-bg px-3 py-2 text-sm font-mono outline-none focus:border-border-light"
              placeholder="# Заголовок\n\nТекст..."
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={saving}>
              Отмена
            </Button>
            <Button variant="primary" onClick={() => void createFile()} disabled={saving}>
              Создать
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
