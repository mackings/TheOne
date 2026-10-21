"use client";

/** Ziva, TheOne's assistant. One conversation for the whole console: a call keeps going while the analyst moves
 * between pages, and Ziva always knows which page is open. */
import { usePathname, useRouter } from "next/navigation";
import { createContext, Suspense, useCallback, useContext, useEffect, useRef, useState } from "react";

import type { UiAction } from "@/domain/assistant";
import type { RingDetail } from "@/domain/network";
import { useAssistant } from "@/presentation/hooks/gateways";
import { type Msg, useVoiceConversation, type VoiceState } from "@/presentation/hooks/useVoiceConversation";

type Listener = (spoken: string) => void;

type Ziva = {
  msgs: Msg[];
  voice: VoiceState;
  level: number;
  busy: boolean;
  onCall: boolean;
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  call: (ring?: string) => void;
  endCall: () => void;
  ask: (text: string) => void;
  /** Have Ziva explain how a ring's fraud took place: opens a call on that ring, or asks on the call already open. */
  explainRing: (ring: RingDetail) => void;
  /** The account the analyst has selected on screen, so "this account" means it. */
  focusAccount: (accountId: string | null) => void;
  /** Hear what Ziva says as she says it. Returns the unsubscribe function. */
  listen: (fn: Listener) => () => void;
};

const ZivaContext = createContext<Ziva | null>(null);

export function useZiva(): Ziva {
  const z = useContext(ZivaContext);
  if (!z) throw new Error("ZivaProvider is missing above this component");
  return z;
}

export function ZivaProvider({ children }: { children: React.ReactNode }) {
  const assistant = useAssistant();
  const router = useRouter();
  const [panelOpen, setPanelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const listeners = useRef(new Set<Listener>());
  const page = useRef<{ path: string; account: string | null }>({ path: "", account: null });

  const act = useCallback((ui: UiAction) => ui.navigate && router.push(ui.navigate), [router]);
  const tell = useCallback((spoken: string) => listeners.current.forEach((fn) => fn(spoken)), []);
  const conversation = useVoiceConversation({ onUi: act, onSpoken: tell, onReady: () => conversation.sendPage(page.current) });
  const { msgs, add, voice, level, start, stop, say, sendPage } = conversation;
  const onCall = voice !== "off";

  const listen = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  const send = useRef(sendPage);
  useEffect(() => {
    send.current = sendPage;
  }, [sendPage]);
  const report = useCallback((next: Partial<typeof page.current>) => {
    page.current = { ...page.current, ...next };
    send.current(page.current);
  }, []);
  const focusAccount = useCallback((account: string | null) => report({ account }), [report]);

  function endCall() {
    stop();
    tell("");
  }

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy || say(q)) return;
    const history = [...msgs.filter((m) => m.role === "user" || m.role === "assistant"), { role: "user" as const, text: q }]
      .slice(-12)
      .map((m) => ({ role: m.role as "user" | "assistant", text: m.text }));
    add("user", q);
    setBusy(true);
    try {
      const r = await assistant.chat(history);
      r.steps.forEach((s) => add("step", s));
      add("assistant", r.reply);
      r.ui.forEach(act);
    } catch (e) {
      add("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function explainRing(ring: RingDetail) {
    setPanelOpen(true);
    if (onCall) say(`Please explain how the fraud in ring ${ring.number ?? ring.id} took place.`);
    else start(ring.id);
  }

  const value: Ziva = {
    msgs, voice, level, busy, onCall, panelOpen, setPanelOpen,
    call: (ring) => {
      setPanelOpen(true);
      start(ring);
    },
    endCall,
    ask,
    explainRing,
    focusAccount,
    listen,
  };

  return (
    <ZivaContext.Provider value={value}>
      <Suspense fallback={null}>
        <PageReporter onPage={(path) => report({ path, account: null })} />
      </Suspense>
      {children}
    </ZivaContext.Provider>
  );
}

function PageReporter({ onPage }: { onPage: (path: string) => void }) {
  const path = usePathname();
  const latest = useRef(onPage);
  useEffect(() => {
    latest.current = onPage;
  }, [onPage]);
  useEffect(() => {
    latest.current(path);
  }, [path]);
  return null;
}
