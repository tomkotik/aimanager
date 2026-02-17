"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

type SidebarProps = {
  mobileOpen: boolean;
  onMobileClose: () => void;
};

type NavItem = {
  href: string;
  label: string;
};

const NAV: NavItem[] = [
  { href: "/agents", label: "🤖 Агенты" },
  { href: "/knowledge", label: "📚 База знаний" },
  { href: "/conversations", label: "💬 Диалоги" },
  { href: "/secrets", label: "🔑 Секреты" },
  { href: "/analytics", label: "📊 Аналитика" },
  { href: "/reliability", label: "🛡️ Надёжность" },
  { href: "/chat", label: "🧪 Тестовый чат" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await apiFetch<{ status: string }>("/health");
        if (!cancelled) setBackendOk(res.status === "ok");
      } catch {
        if (!cancelled) setBackendOk(false);
      }
    }
    void check();
    const id = window.setInterval(check, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <>
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={onMobileClose}
        />
      ) : null}

      <aside
        className={[
          "fixed z-50 inset-y-0 left-0 w-[280px] border-r border-border bg-bg-card md:static md:z-auto",
          "transform transition-transform duration-200 md:transform-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        ].join(" ")}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between px-4 py-4 md:px-6">
            <div className="flex flex-col">
              <div className="font-mono text-lg tracking-tight">AgentBox</div>
              <div className="text-xs text-text-dim">Панель управления</div>
            </div>

            <button
              type="button"
              className="md:hidden rounded-lg border border-border px-2 py-1 text-xs text-text-muted hover:bg-bg-hover transition-colors"
              onClick={onMobileClose}
            >
              Закрыть
            </button>
          </div>

          <nav className="flex-1 px-2 md:px-4">
            <ul className="flex flex-col gap-1">
              {NAV.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onMobileClose}
                      className={[
                        "block rounded-lg px-3 py-2 text-sm transition-colors",
                        active
                          ? "bg-bg-hover text-text border border-border-light"
                          : "text-text-muted hover:bg-bg-hover hover:text-text",
                      ].join(" ")}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="border-t border-border px-4 py-4 md:px-6">
            <div className="flex items-center gap-2 text-xs text-text-dim">
              <span
                className={[
                  "inline-block h-2 w-2 rounded-full",
                  backendOk === null ? "bg-warning" : backendOk ? "bg-accent" : "bg-danger",
                ].join(" ")}
              />
              Сервер: {backendOk === null ? "проверка..." : backendOk ? "подключён" : "не отвечает"}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
