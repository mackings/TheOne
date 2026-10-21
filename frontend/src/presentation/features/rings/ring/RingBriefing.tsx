"use client";

/** A spoken walk-through of one ring: TheOne explains how the fraud happened, lights up each account on the map as it
 * names it, and answers questions about the ring by voice or text. */
import { AudioLines, Loader2, Mic, Send, Square, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { RingDetail } from "@/domain/network";
import { cx } from "@/presentation/cx";
import { ringName } from "@/presentation/format";
import { useVoiceConversation } from "@/presentation/hooks/useVoiceConversation";

/** The account named last in what has been said so far: its full name, or its surname when no other account shares it. */
function lastNamed(text: string, names: { id: string; full: string; surname: string | null }[]): string | null {
  const t = text.toLowerCase();
  let best: { id: string; at: number } | null = null;
  for (const n of names) {
    const at = Math.max(t.lastIndexOf(n.full), n.surname ? t.lastIndexOf(n.surname) : -1);
    if (at >= 0 && (!best || at > best.at)) best = { id: n.id, at };
  }
  return best?.id ?? null;
}

export function RingBriefing({ ring, onSpotlight, onClose }: {
  ring: RingDetail;
  onSpotlight: (nodeId: string | null) => void;
  onClose: () => void;
}) {
  const names = useMemo(() => {
    const named = ring.nodes.filter((n) => n.name?.trim());
    const surnames = named.map((n) => n.name.trim().split(/\s+/).pop()!.toLowerCase());
    return named.map((n, i) => ({
      id: n.id,
      full: n.name.trim().toLowerCase(),
      surname: surnames.filter((s) => s === surnames[i]).length === 1 && surnames[i].length > 3 ? surnames[i] : null,
    }));
  }, [ring.nodes]);
  const lit = useRef<string | null>(null);
  const { msgs, voice, level, start, stop, say } = useVoiceConversation({
    ring: ring.id,
    onSpoken: (text) => {
      const id = lastNamed(text, names);
      if (id && id !== lit.current) {
        lit.current = id;
        onSpotlight(id);
      }
    },
  });
  const [input, setInput] = useState("");
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = requestAnimationFrame(() => start());
    document.body.dataset.briefing = "true";
    return () => {
      cancelAnimationFrame(id);
      delete document.body.dataset.briefing;
    };
    // Start once, when the panel opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  function close() {
    stop();
    onSpotlight(null);
    onClose();
  }

  function ask(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (q && say(q)) setInput("");
  }

  const state = voice === "connecting" ? "Connecting…" : voice === "speaking" ? "Speaking" : voice === "listening" ? "Listening: ask anything about this ring" : "Stopped";

  return (
    <section
      className="fixed inset-x-0 bottom-0 z-[60] flex max-h-[70vh] flex-col border border-[var(--line)] bg-[var(--surface)] shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:max-h-[min(440px,calc(100vh-6rem))] sm:w-[400px] sm:rounded-[8px]"
      style={{ animation: "toast-in 160ms ease-out" }}
      aria-label={`Voice briefing on ${ringName(ring)}`}
    >
      <header className="flex items-center gap-3 border-b border-[var(--line)] px-4 py-3">
        <div className="relative flex size-9 items-center justify-center rounded-full bg-[var(--brand)] text-white">
          {voice === "connecting" ? <Loader2 className="size-4 animate-spin" /> : <AudioLines className={cx("size-4", voice === "speaking" && "animate-pulse")} />}
          {voice === "listening" && (
            <span className="pointer-events-none absolute inset-0 rounded-full border-2 border-[var(--brand)]" style={{ transform: `scale(${1 + level * 0.4})`, opacity: 0.5 }} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{ringName(ring)}, talked through</div>
          <div className="text-xs text-[var(--muted)]">{state}</div>
        </div>
        <button className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)]" onClick={close} aria-label="Close the briefing">
          <X className="size-4" />
        </button>
      </header>

      <div ref={list} className="min-h-[140px] flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
        {!msgs.length && <p className="text-sm text-[var(--muted)]">TheOne is getting ready to explain how this fraud happened…</p>}
        {msgs.filter((m) => m.role !== "step").map((m) => (
          <div key={m.id} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cx(
                "max-w-[88%] whitespace-pre-wrap rounded-[8px] px-3 py-2 text-sm leading-relaxed",
                m.role === "user" && "bg-[var(--ink)] text-[var(--surface)]",
                m.role === "assistant" && "bg-[var(--surface-2)] text-[var(--ink)]",
                m.role === "error" && "bg-[var(--critical-soft)] text-[var(--ink)]",
              )}
            >
              {m.text}
              {m.live && <span className="ml-1 inline-block size-1.5 animate-pulse rounded-full bg-current align-middle opacity-60" />}
            </div>
          </div>
        ))}
      </div>

      <form className="flex items-center gap-2 border-t border-[var(--line)] p-3" onSubmit={ask}>
        <button
          type="button"
          onClick={() => (voice === "off" ? start() : stop())}
          className={cx(
            "flex size-10 shrink-0 items-center justify-center rounded-full border transition-colors",
            voice === "off" ? "border-[var(--line-strong)] text-[var(--ink-2)] hover:border-[var(--brand)] hover:text-[var(--brand)]" : "border-transparent bg-[var(--brand)] text-white",
          )}
          aria-label={voice === "off" ? "Start the briefing again" : "Stop talking"}
          title={voice === "off" ? "Start again" : "Stop"}
        >
          {voice === "off" ? <Mic className="size-4" /> : <Square className="size-3.5 fill-current" />}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={voice === "off" ? "Start the briefing to ask" : "Ask out loud, or type a question"}
          disabled={voice === "off" || voice === "connecting"}
          className="h-10 min-w-0 flex-1 rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm outline-none focus:border-[var(--brand)] disabled:opacity-60"
          aria-label="Question about this ring"
        />
        <button type="submit" disabled={!input.trim() || voice === "off"} className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--brand)] text-white disabled:opacity-40" aria-label="Ask">
          <Send className="size-4" />
        </button>
      </form>
    </section>
  );
}
