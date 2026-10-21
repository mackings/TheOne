"use client";

/** Ziva on screen: a launcher, a small call pill while a call runs in the background, and the full conversation panel. */
import { ChevronDown, Loader2, Phone, PhoneOff, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cx } from "@/presentation/cx";
import { useAsync } from "@/presentation/hooks/useAsync";
import { useAssistant } from "@/presentation/hooks/gateways";
import { useZiva } from "./ZivaProvider";

const SUGGESTIONS = ["What needs my attention today?", "Explain the riskiest ring", "Why was this account flagged?"];

function Avatar({ size = "size-9", level = 0, live = false }: { size?: string; level?: number; live?: boolean }) {
  return (
    <span className={cx("relative flex shrink-0 items-center justify-center rounded-full bg-[var(--brand)] font-semibold text-white", size)}>
      Z
      {live && (
        <span className="pointer-events-none absolute inset-0 rounded-full border-2 border-[var(--brand)]" style={{ transform: `scale(${1.1 + level * 0.4})`, opacity: 0.5 }} />
      )}
    </span>
  );
}

export function ZivaWidget() {
  const assistant = useAssistant();
  const status = useAsync(() => assistant.status());
  const z = useZiva();
  const [input, setInput] = useState("");
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [z.msgs, z.panelOpen]);

  if (status.data && !status.data.enabled) return null;

  const state = z.voice === "connecting" ? "Calling…" : z.voice === "speaking" ? "Speaking" : z.voice === "listening" ? "Listening" : null;

  if (!z.panelOpen) {
    if (z.onCall)
      return (
        <div className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface)] py-1.5 pl-1.5 pr-2 shadow-lg">
          <button className="flex items-center gap-2.5 pr-1" onClick={() => z.setPanelOpen(true)} aria-label="Open the call with Ziva">
            <Avatar level={z.level} live={z.voice === "listening"} />
            <span className="text-left leading-tight">
              <span className="block text-sm font-semibold">Ziva</span>
              <span className="block text-xs text-[var(--muted)]">{state}</span>
            </span>
          </button>
          <button className="flex size-9 items-center justify-center rounded-full bg-[var(--critical)] text-white hover:opacity-90" onClick={z.endCall} aria-label="End the call" title="End call">
            <PhoneOff className="size-4" />
          </button>
        </div>
      );
    return (
      <button
        onClick={() => z.setPanelOpen(true)}
        className="fixed bottom-5 right-5 z-40 inline-flex h-12 items-center gap-2 rounded-full bg-[var(--brand)] pl-1.5 pr-5 text-sm font-semibold text-white shadow-lg hover:bg-[var(--brand-strong)] [body[data-fullscreen]_&]:hidden"
      >
        <span className="flex size-9 items-center justify-center rounded-full bg-white/20">Z</span>
        Ask Ziva
      </button>
    );
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    z.ask(input);
    setInput("");
  }

  return (
    <section
      className="fixed inset-x-0 bottom-0 z-[60] flex h-[75vh] flex-col border border-[var(--line)] bg-[var(--surface)] shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:h-[600px] sm:max-h-[calc(100vh-6rem)] sm:w-[400px] sm:rounded-[8px]"
      style={{ animation: "toast-in 160ms ease-out" }}
      aria-label="Ziva"
    >
      <header className="flex items-center gap-3 border-b border-[var(--line)] px-4 py-3">
        <Avatar level={z.level} live={z.voice === "listening"} />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Ziva</div>
          <div className="text-xs text-[var(--muted)]">{state ? `On a call · ${state}` : "TheOne's assistant. Type, or call to talk"}</div>
        </div>
        <button className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)]" onClick={() => z.setPanelOpen(false)} aria-label="Minimise Ziva" title={z.onCall ? "Minimise; the call carries on" : "Minimise"}>
          <ChevronDown className="size-4" />
        </button>
      </header>

      <div ref={list} className="flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
        {!z.msgs.length && (
          <div className="space-y-3">
            <p className="text-sm text-[var(--ink-2)]">
              I&apos;m Ziva. Ask me about rings, accounts, alerts or payments. Call me and I&apos;ll stay on the line while you move around the console.
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => z.ask(s)} className="rounded-full border border-[var(--line-strong)] px-3 py-1.5 text-xs hover:border-[var(--brand)] hover:text-[var(--brand)]">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {z.msgs.map((m) =>
          m.role === "step" ? (
            <div key={m.id} className="flex items-center gap-1.5 pl-1 text-[11px] text-[var(--muted)]">
              <span className="size-1 rounded-full bg-[var(--muted)]" />
              {m.text}
            </div>
          ) : (
            <div key={m.id} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cx(
                  "max-w-[85%] whitespace-pre-wrap rounded-[8px] px-3 py-2 text-sm leading-relaxed",
                  m.role === "user" && "bg-[var(--ink)] text-[var(--surface)]",
                  m.role === "assistant" && "bg-[var(--surface-2)] text-[var(--ink)]",
                  m.role === "error" && "bg-[var(--critical-soft)] text-[var(--ink)]",
                )}
              >
                {m.text}
                {m.live && <span className="ml-1 inline-block size-1.5 animate-pulse rounded-full bg-current align-middle opacity-60" />}
              </div>
            </div>
          ),
        )}
        {z.busy && (
          <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <Loader2 className="size-3.5 animate-spin" /> Looking that up…
          </div>
        )}
      </div>

      <form className="flex items-center gap-2 border-t border-[var(--line)] p-3" onSubmit={submit}>
        <button
          type="button"
          onClick={() => (z.onCall ? z.endCall() : z.call())}
          className={cx(
            "flex size-10 shrink-0 items-center justify-center rounded-full text-white transition-colors",
            z.onCall ? "bg-[var(--critical)] hover:opacity-90" : "bg-[var(--good)] hover:opacity-90",
          )}
          aria-label={z.onCall ? "End the call" : "Call Ziva"}
          title={z.onCall ? "End call" : "Call Ziva"}
        >
          {z.voice === "connecting" ? <Loader2 className="size-4 animate-spin" /> : z.onCall ? <PhoneOff className="size-4" /> : <Phone className="size-4" />}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={z.onCall ? "Talk, or type while on the call" : "Ask Ziva a question"}
          className="h-10 min-w-0 flex-1 rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm outline-none focus:border-[var(--brand)]"
          aria-label="Question for Ziva"
        />
        <button type="submit" disabled={!input.trim() || z.busy} className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--brand)] text-white disabled:opacity-40" aria-label="Send">
          <Send className="size-4" />
        </button>
      </form>
    </section>
  );
}
