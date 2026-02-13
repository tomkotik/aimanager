"use client";

import { PropsWithChildren, useState } from "react";

import { Sidebar } from "@/components/Sidebar";
import { ToastProvider } from "@/components/ToastProvider";

export function AppShell({ children }: PropsWithChildren) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="min-h-screen bg-bg text-text">
        <div className="flex min-h-screen">
          <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 border-b border-border bg-bg/70 backdrop-blur">
              <div className="flex items-center justify-between px-4 py-3 md:px-6">
                <button
                  type="button"
                  className="md:hidden inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-text-muted hover:bg-bg-hover transition-colors"
                  onClick={() => setMobileOpen(true)}
                >
                  <span className="font-mono">МЕНЮ</span>
                </button>

                <div className="hidden md:block text-sm text-text-dim">
                  Панель управления агентами
                </div>
              </div>
            </header>

            <main className="flex-1 px-4 py-6 md:px-6">{children}</main>
          </div>
        </div>
      </div>
    </ToastProvider>
  );
}
