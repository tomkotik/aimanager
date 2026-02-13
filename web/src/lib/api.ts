const ENV_API_BASE = process.env.NEXT_PUBLIC_API_URL;

function resolveApiBase(): string {
  // In Docker Compose, frontend container can reach backend as `http://app:8000`,
  // but the browser running on the host machine cannot resolve `app`.
  if (typeof window !== "undefined") {
    // If not configured explicitly, default to same-origin API (production behind a reverse proxy).
    if (!ENV_API_BASE) return window.location.origin;

    try {
      const u = new URL(ENV_API_BASE);
      if (u.hostname === "app") return "http://localhost:8000";
    } catch {
      // Ignore URL parse errors and fall back to env value.
    }
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

    if (detail === "Tenant not found") return "Тенант не найден";
    if (detail.startsWith("Tenant config not found:")) {
      const rest = detail.slice("Tenant config not found:".length).trim();
      return rest ? `Не найден конфиг тенанта: ${rest}` : "Не найден конфиг тенанта";
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

    throw new ApiError(res.status, typeof detail === "string" ? detail : `API error: ${res.status}`, {
      detail,
      body,
    });
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
