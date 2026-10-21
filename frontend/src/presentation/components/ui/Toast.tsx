"use client";

import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { TONE, type Tone } from "./Badge";

type ToastKind = "success" | "error" | "info" | "warning";
type ToastItem = { id: number; kind: ToastKind; title: string; description?: string };
const ToastCtx = createContext<{ push: (kind: ToastKind, title: string, description?: string) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((kind: ToastKind, title: string, description?: string) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-3), { id, kind, title, description }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4500);
  }, []);
  const icon = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle };
  const tone: Record<ToastKind, Tone> = { success: "good", error: "critical", info: "info", warning: "warning" };
  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed right-4 top-16 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2" aria-live="polite">
        {items.map((t) => {
          const Icon = icon[t.kind];
          return (
            <div
              key={t.id}
              className="pointer-events-auto flex items-start gap-3 rounded-[8px] border border-[var(--line)] bg-[var(--surface)] p-3 shadow-lg"
              style={{ animation: "toast-in 160ms ease-out", borderLeft: `4px solid ${TONE[tone[t.kind]].dot}` }}
              role={t.kind === "error" ? "alert" : "status"}
            >
              <Icon className="mt-0.5 size-4 shrink-0" style={{ color: TONE[tone[t.kind]].dot }} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{t.title}</div>
                {t.description && <div className="mt-0.5 text-xs text-[var(--muted)]">{t.description}</div>}
              </div>
              <button className="rounded p-0.5 text-[var(--muted)] hover:text-[var(--ink)]" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))} aria-label="Dismiss">
                <X className="size-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  return useMemo(
    () => ({
      success: (t: string, d?: string) => ctx?.push("success", t, d),
      error: (t: string, d?: string) => ctx?.push("error", t, d),
      info: (t: string, d?: string) => ctx?.push("info", t, d),
      warning: (t: string, d?: string) => ctx?.push("warning", t, d),
    }),
    [ctx],
  );
}
