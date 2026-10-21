"use client";

/** A live voice conversation with the assistant: the transcript, whether it is listening or speaking, and the mic level. */
import { useEffect, useRef, useState } from "react";

import type { LiveSession } from "@/application/ports";
import type { LiveEvent, UiAction } from "@/domain/assistant";
import { useAssistant } from "@/presentation/hooks/gateways";

export type Msg = { id: number; role: "user" | "assistant" | "step" | "error"; text: string; live?: boolean };
export type VoiceState = "off" | "connecting" | "listening" | "speaking";

export function useVoiceConversation({ onUi, onSpoken, onReady }: {
  onUi?: (ui: UiAction) => void;
  /** Everything the assistant has said in its current turn so far. */
  onSpoken?: (text: string) => void;
  onReady?: () => void;
} = {}) {
  const assistant = useAssistant();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [voice, setVoice] = useState<VoiceState>("off");
  const [level, setLevel] = useState(0);
  const live = useRef<LiveSession | null>(null);
  const seq = useRef(0);
  const spoken = useRef("");
  const handlers = useRef({ onUi, onSpoken, onReady });

  useEffect(() => {
    handlers.current = { onUi, onSpoken, onReady };
  }, [onUi, onSpoken, onReady]);

  const add = (role: Msg["role"], text: string) => setMsgs((xs) => [...xs, { id: ++seq.current, role, text }]);

  // Streamed transcripts grow the current bubble of that speaker until the turn completes.
  const grow = (role: "user" | "assistant", text: string) =>
    setMsgs((xs) => {
      const last = xs[xs.length - 1];
      if (last && last.role === role && last.live) return [...xs.slice(0, -1), { ...last, text: last.text + text }];
      return [...xs.map((x) => (x.live ? { ...x, live: false } : x)), { id: ++seq.current, role, text, live: true }];
    });

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

  function onEvent(e: LiveEvent) {
    if (e.type === "ready") {
      setVoice("listening");
      handlers.current.onReady?.();
    } else if (e.type === "user_text") grow("user", e.text);
    else if (e.type === "assistant_text") {
      grow("assistant", e.text);
      spoken.current += e.text;
      handlers.current.onSpoken?.(spoken.current);
    } else if (e.type === "step") add("step", e.text);
    else if (e.type === "ui") handlers.current.onUi?.(e.action);
    else if (e.type === "speaking") setVoice((v) => (v === "off" ? v : e.on ? "speaking" : "listening"));
    else if (e.type === "turn_complete") {
      spoken.current = "";
      setMsgs((xs) => xs.map((x) => (x.live ? { ...x, live: false } : x)));
    } else if (e.type === "error") add("error", e.text);
    else if (e.type === "closed") {
      live.current = null;
      setVoice("off");
    }
  }

  /** Start a call; with `ring` it opens with an explanation of that ring. */
  async function start(ring?: string) {
    if (live.current) return;
    setVoice("connecting");
    const session = assistant.live(onEvent, { ring });
    live.current = session;
    try {
      await session.start();
    } catch (e) {
      live.current = null;
      setVoice("off");
      add("error", (e as Error).message.includes("Permission") ? "Microphone permission was refused." : (e as Error).message);
    }
  }

  function stop() {
    live.current?.stop();
    live.current = null;
    setVoice("off");
  }

  /** Type a question into the live conversation. Returns false when no session is open. */
  function say(text: string): boolean {
    if (!live.current?.open) return false;
    add("user", text);
    live.current.sendText(text);
    return true;
  }

  function sendPage(page: { path: string; account?: string | null }) {
    if (live.current?.open) live.current.sendPage(page);
  }

  return { msgs, add, voice, level, start, stop, say, sendPage };
}
