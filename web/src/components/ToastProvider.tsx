"use client";

import {
  PropsWithChildren,
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

type ToastVariant = "success" | "error" | "info";

export type Toast = {
  id: string;
  title: string;
  message?: string;
  variant: ToastVariant;
};

type ToastContextValue = {
  push: (toast: Omit<Toast, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

function variantClasses(variant: ToastVariant): { border: string; dot: string } {
  if (variant === "success") return { border: "border-accent/40", dot: "bg-accent" };
  if (variant === "error") return { border: "border-danger/40", dot: "bg-danger" };
  return { border: "border-border-light", dot: "bg-warning" };
}

export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const push = useCallback((toast: Omit<Toast, "id">) => {
    counter.current += 1;
    const id = `${Date.now()}-${counter.current}`;
    const next: Toast = { id, ...toast };

    setToasts((prev) => [next, ...prev].slice(0, 5));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}

      <div className="fixed right-4 top-4 z-[100] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => {
          const cls = variantClasses(t.variant);
          return (
            <div
              key={t.id}
              className={[
                "rounded-xl border bg-bg-card px-4 py-3 shadow-lg",
                "animate-fade-in",
                cls.border,
              ].join(" ")}
            >
              <div className="flex items-start gap-3">
                <span className={`mt-1 h-2.5 w-2.5 rounded-full ${cls.dot}`} />
                <div className="min-w-0">
                  <div className="truncate text-sm font-mono text-text">{t.title}</div>
                  {t.message ? (
                    <div className="mt-1 text-xs text-text-muted">{t.message}</div>
                  ) : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
