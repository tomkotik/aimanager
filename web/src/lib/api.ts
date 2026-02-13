const ENV_API_BASE = process.env.NEXT_PUBLIC_API_URL;

function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    // В браузере: используем тот же домен если env не задан или указывает на docker-internal.
    const envUrl = ENV_API_BASE || "";
    if (!envUrl || envUrl.includes("app:")) return window.location.origin;
    return envUrl;
  }
  return ENV_API_BASE || "http://localhost:8000";
}

const API_BASE = resolveApiBase();

export class ApiError extends Error {
  status: number;
  detail: unknown;
  body: unknown;

  constructor(status: number, message: string, opts?: { detail?: unknown; body?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = opts?.detail;
    this.body = opts?.body;
  }
}

export function formatApiErrorRu(err: unknown, fallback = "Неизвестная ошибка"): string {
  if (err instanceof ApiError) {
    const detail = typeof err.detail === "string" ? err.detail : err.message;

    if (detail === "Tenant not found") return "Клиент не найден";
    if (detail.startsWith("Tenant config not found:")) {
      const rest = detail.slice("Tenant config not found:".length).trim();
      return rest ? `Не найдены настройки клиента: ${rest}` : "Не найдены настройки клиента";
    }
    if (detail === "Agent already exists") return "Агент уже существует";

    return detail || `Ошибка API: ${err.status}`;
  }

  if (err instanceof Error) {
    if (err.message === "Failed to fetch") return "Ошибка сети: не удалось подключиться к API";
    return err.message || fallback;
  }

  return fallback;
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let body: unknown = text;
    try {
      body = text ? (JSON.parse(text) as unknown) : undefined;
    } catch {
      // Keep raw text as body.
    }

    const detail =
      body && typeof body === "object" && "detail" in body ? (body as { detail?: unknown }).detail : undefined;

    throw new ApiError(res.status, typeof detail === "string" ? detail : `Ошибка API: ${res.status}`, {
      detail,
      body,
    });
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
