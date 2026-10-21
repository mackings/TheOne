"use client";

import { Loader2, Mic, MicOff, Send, Sparkles, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { cx } from "@/presentation/cx";
import { useAsync } from "@/presentation/hooks/useAsync";
import type { LiveEvent, UiAction } from "@/domain/assistant";
import type { LiveSession } from "@/application/ports";
import { useAssistant } from "@/presentation/hooks/gateways";

type Msg = { id: number; role: "user" | "assistant" | "step" | "error"; text: string; live?: boolean };
type Voice = "off" | "connecting" | "listening" | "speaking";

const SUGGESTIONS = ["What needs my attention today?", "Show me the riskiest ring", "Why was this account flagged?"];

/** "Ask TheOne": text chat, or a live voice conversation, about rings, accounts, alerts and payments. */
export function Assistant() {
  const assistantApi = useAssistant();
  const router = useRouter();
  const status = useAsync(() => assistantApi.status());
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [voice, setVoice] = useState<Voice>("off");
  const [level, setLevel] = useState(0);
  const live = useRef<LiveSession | null>(null);
  const seq = useRef(0);
  const list = useRef<HTMLDivElement>(null);

  const add = (role: Msg["role"], text: string, liveMsg = false) =>
    setMsgs((xs) => [...xs, { id: ++seq.current, role, text, live: liveMsg }]);

  // Streamed transcripts grow the current bubble of that speaker until the turn completes.
  const grow = (role: "user" | "assistant", text: string) =>
    setMsgs((xs) => {
      const last = xs[xs.length - 1];
      if (last && last.role === role && last.live) return [...xs.slice(0, -1), { ...last, text: last.text + text }];
      return [...xs.map((x) => (x.live ? { ...x, live: false } : x)), { id: ++seq.current, role, text, live: true }];
    });

  const act = (ui: UiAction) => ui.navigate && router.push(ui.navigate);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  useEffect(() => {
    if (voice === "off") return;
    let raf = 0;
    const tick = () => {
      setLevel(live.current?.level ?? 0);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [voice]);

  useEffect(() => () => live.current?.stop(), []);

  function onLive(e: LiveEvent) {
    if (e.type === "ready") setVoice("listening");
    else if (e.type === "user_text") grow("user", e.text);
    else if (e.type === "assistant_text") grow("assistant", e.text);
    else if (e.type === "step") add("step", e.text);
    else if (e.type === "ui") act(e.action);
    else if (e.type === "speaking") setVoice((v) => (v === "off" ? v : e.on ? "speaking" : "listening"));
    else if (e.type === "turn_complete") setMsgs((xs) => xs.map((x) => (x.live ? { ...x, live: false } : x)));
    else if (e.type === "error") add("error", e.text);
    else if (e.type === "closed") {
      live.current = null;
      setVoice("off");
    }
  }

  async function toggleVoice() {
    if (live.current) {
      live.current.stop();
      live.current = null;
      setVoice("off");
      return;
    }
    setVoice("connecting");
    const v = assistantApi.live(onLive);
    live.current = v;
    try {
      await v.start();
    } catch (e) {
      live.current = null;
      setVoice("off");
      add("error", (e as Error).message.includes("Permission") ? "Microphone permission was refused." : (e as Error).message);
    }
  }

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    if (live.current?.open) {
      add("user", q);
      live.current.sendText(q);
      return;
    }
    const history = [...msgs.filter((m) => m.role === "user" || m.role === "assistant"), { role: "user" as const, text: q }]
      .slice(-12)
      .map((m) => ({ role: m.role as "user" | "assistant", text: m.text }));
    add("user", q);
    setBusy(true);
    try {
      const r = await assistantApi.chat(history);
      r.steps.forEach((s) => add("step", s));
      add("assistant", r.reply);
      r.ui.forEach(act);
    } catch (e) {
      add("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (status.data && !status.data.enabled) return null;

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-40 inline-flex h-12 [body[data-fullscreen]_&]:hidden items-center gap-2 rounded-full bg-[var(--brand)] px-5 text-sm font-semibold text-white shadow-lg hover:bg-[var(--brand-strong)]"
        >
          <Sparkles className="size-4" />
          Ask TheOne
        </button>
      )}
      {open && (
        <section
          className="fixed inset-x-0 bottom-0 z-40 flex h-[75vh] flex-col border border-[var(--line)] bg-[var(--surface)] shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:h-[620px] sm:max-h-[calc(100vh-6rem)] sm:w-[400px] sm:rounded-[8px]"
          style={{ animation: "toast-in 160ms ease-out" }}
          aria-label="TheOne assistant"
        >
          <header className="flex items-center gap-3 border-b border-[var(--line)] px-4 py-3">
            <div className="flex size-8 items-center justify-center rounded-full bg-[var(--brand)]">
              <Sparkles className="size-4 text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">TheOne assistant</div>
              <div className="text-xs text-[var(--muted)]">
                {voice === "off" ? "Ask by typing, or tap the mic to talk" : voice === "connecting" ? "Connecting…" : voice === "speaking" ? "Speaking…" : "Listening…"}
              </div>
            </div>
            <button className="rounded p-1.5 text-[var(--muted)] hover:bg-[var(--surface-2)]" onClick={() => { live.current?.stop(); setOpen(false); }} aria-label="Close assistant">
              <X className="size-4" />
            </button>
          </header>

          <div ref={list} className="flex-1 space-y-2.5 overflow-y-auto px-4 py-4">
            {!msgs.length && (
              <div className="space-y-3">
                <p className="text-sm text-[var(--ink-2)]">
                  Ask about rings, accounts, alerts or payments. Answers come from TheOne&apos;s data. The assistant can&apos;t take actions; those stay as buttons in the console.
                </p>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-full border border-[var(--line-strong)] px-3 py-1.5 text-xs hover:border-[var(--brand)] hover:text-[var(--brand)]">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m) =>
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
            {busy && (
              <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                <Loader2 className="size-3.5 animate-spin" /> Looking that up…
              </div>
            )}
          </div>

          <form
            className="flex items-center gap-2 border-t border-[var(--line)] p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <button
              type="button"
              onClick={toggleVoice}
              className={cx(
                "relative flex size-10 shrink-0 items-center justify-center rounded-full border transition-colors",
                voice === "off" ? "border-[var(--line-strong)] text-[var(--ink-2)] hover:border-[var(--brand)] hover:text-[var(--brand)]" : "border-transparent bg-[var(--brand)] text-white",
              )}
              aria-label={voice === "off" ? "Start talking" : "Stop talking"}
              title={voice === "off" ? "Talk to TheOne" : "Stop"}
            >
              {voice === "connecting" ? <Loader2 className="size-4 animate-spin" /> : voice === "off" ? <Mic className="size-4" /> : <MicOff className="size-4" />}
              {voice === "listening" && (
                <span className="pointer-events-none absolute inset-0 rounded-full border-2 border-[var(--brand)]" style={{ transform: `scale(${1 + level * 0.35})`, opacity: 0.5 }} />
              )}
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={voice === "off" ? "Ask a question" : "Or type while talking"}
              className="h-10 min-w-0 flex-1 rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-sm outline-none focus:border-[var(--brand)]"
              aria-label="Question"
            />
            <button type="submit" disabled={!input.trim() || busy} className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--brand)] text-white disabled:opacity-40" aria-label="Send">
              <Send className="size-4" />
            </button>
          </form>
        </section>
      )}
    </>
  );
}
