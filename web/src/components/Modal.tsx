"use client";

import { PropsWithChildren, useEffect } from "react";

type ModalProps = PropsWithChildren<{
  title: string;
  open: boolean;
  onClose: () => void;
}>;

export function Modal({ title, open, onClose, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="w-full max-w-xl rounded-xl border border-border bg-bg-card shadow-xl animate-zoom-in">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="font-mono text-sm text-text">{title}</div>
            <button
              type="button"
              className="rounded-lg border border-border px-2 py-1 text-xs text-text-muted hover:bg-bg-hover transition-colors"
              onClick={onClose}
            >
              Закрыть
            </button>
          </div>
          <div className="px-4 py-4">{children}</div>
        </div>
      </div>
    </div>
  );
}
