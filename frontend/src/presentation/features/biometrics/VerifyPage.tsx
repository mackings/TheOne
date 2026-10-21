"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CONTEXTS } from "@/domain/identity";
import { Recorder } from "@/infrastructure/media/recorder";
import { Button, Card, DecisionBadge, ErrorText, LevelMeter, QualityLine, ScoreBar } from "./parts";
import type { ContinuousSession, Customer, Health, VerifyResult } from "@/domain/identity";
import { useIdentity } from "@/presentation/hooks/gateways";

const CHUNK_MS = 3000;

export function VerifyPage() {
  return (
    <Suspense fallback={null}>
      <VerifyInner />
    </Suspense>
  );
}

function VerifyInner() {
  const api = useIdentity();
  const params = useSearchParams();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState(params.get("customer") ?? "");
  const [context, setContext] = useState("");
  const [mode, setMode] = useState<"oneshot" | "continuous">("oneshot");
  const [health, setHealth] = useState<Health | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [level, setLevel] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [cont, setCont] = useState<ContinuousSession | null>(null);
  const [history, setHistory] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recorder | null>(null);
  const raf = useRef(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAt = useRef(0);
  const contRef = useRef<ContinuousSession | null>(null);

  useEffect(() => {
    api.listCustomers().then((cs) => setCustomers(cs.filter((c) => c.enrolled))).catch((e) => setError(e.message));
    api.health().then(setHealth).catch(() => {});
  }, [api]);

  useEffect(() => {
    if (!recording) return;
    const tick = () => {
      setLevel(rec.current?.level ?? 0);
      setSeconds((Date.now() - startedAt.current) / 1000);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [recording]);

  useEffect(() => () => { void stopEverything(); }, []);

  const t = health?.thresholds;
  const highRisk = CONTEXTS.find((c) => c.value === context)?.highRisk ?? false;
  const acceptAt = t ? t.match_accept + (highRisk ? t.high_risk_margin : 0) : 0.55;
  const matchMarks = t ? [{ at: t.match_stepup, label: "step-up" }, { at: acceptAt, label: "accept" }] : [];
  const spoofMarks = t ? [{ at: t.spoof_stepup, label: "step-up" }, { at: t.spoof_reject, label: "reject" }] : [];

  async function stopEverything() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    if (rec.current?.active) await rec.current.stop();
    setRecording(false);
  }

  async function startOneShot() {
    setError(null);
    setResult(null);
    try {
      rec.current = new Recorder();
      await rec.current.start();
      startedAt.current = Date.now();
      setRecording(true);
    } catch (err) {
      setError(`Microphone unavailable: ${(err as Error).message}`);
    }
  }

  async function stopOneShot() {
    if (!rec.current) return;
    setRecording(false);
    setBusy(true);
    try {
      const blob = await rec.current.stop();
      setResult(await api.verify(customerId, blob, context || undefined));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startContinuous() {
    setError(null);
    setResult(null);
    setHistory([]);
    try {
      const session = await api.startContinuous(customerId, context || undefined);
      setCont(session);
      contRef.current = session;
      rec.current = new Recorder();
      await rec.current.start();
      startedAt.current = Date.now();
      setRecording(true);
      timer.current = setInterval(async () => {
        const r = rec.current;
        const s = contRef.current;
        if (!r?.active || !s) return;
        const blob = r.take();
        // Skip chunks under one second: a 44-byte WAV header plus 2 bytes per sample.
        if (blob.size < 44 + r.sampleRate * 2) return;
        try {
          const updated = await api.sendChunk(s.id, blob);
          contRef.current = updated;
          setCont(updated);
          if (updated.last_event) setResult(updated.last_event);
          if (updated.ema_score !== null) setHistory((h) => [...h.slice(-29), updated.ema_score as number]);
        } catch (err) {
          setError((err as Error).message);
        }
      }, CHUNK_MS);
    } catch (err) {
      setError((err as Error).message);
      await stopEverything();
    }
  }

  async function stopContinuous() {
    await stopEverything();
    if (contRef.current) {
      const ended = await api.endContinuous(contRef.current.id).catch(() => null);
      if (ended) setCont(ended);
    }
  }

  const ready = Boolean(customerId);

  return (
    <div className="flex flex-col [&>:last-child]:mb-0 [&>:last-child]:flex-auto">
      <Card title="Who is speaking?">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="grid gap-1 text-sm">
            Customer
            <select
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              disabled={recording}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              <option value="">Select an enrolled customer</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                  {c.external_id ? ` (${c.external_id})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            Action being authorised
            <select
              value={context}
              onChange={(e) => setContext(e.target.value)}
              disabled={recording}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              {CONTEXTS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                  {c.highRisk ? " · high risk" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            Mode
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "oneshot" | "continuous")}
              disabled={recording}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              <option value="oneshot">One-shot (record a phrase)</option>
              <option value="continuous">Continuous (live call)</option>
            </select>
          </label>
        </div>
        {customers.length === 0 && !error && (
          <p className="mt-3 text-sm text-[var(--muted)]">No enrolled customers yet. Enrol one first.</p>
        )}
        <ErrorText error={error} />
      </Card>

      <Card title={mode === "oneshot" ? "Record a phrase" : "Live call"}>
        {recording ? (
          <div className="grid gap-3">
            <LevelMeter level={level} />
            <div className="flex items-center gap-4">
              <Button variant="danger" onClick={mode === "oneshot" ? stopOneShot : stopContinuous}>
                Stop ({seconds.toFixed(0)}s)
              </Button>
              <span className="text-sm text-[var(--muted)]">
                {mode === "oneshot"
                  ? "Say anything for a few seconds, then stop."
                  : `Keep talking. A chunk is scored every ${CHUNK_MS / 1000}s.`}
              </span>
            </div>
          </div>
        ) : (
          <Button onClick={mode === "oneshot" ? startOneShot : startContinuous} disabled={!ready || busy}>
            {busy ? "Scoring…" : mode === "oneshot" ? "Record" : "Start call"}
          </Button>
        )}

        {mode === "continuous" && cont && (
          <div className="mt-5 grid gap-2">
            <div className="flex items-center gap-3">
              <span
                className="rounded-full px-3 py-1 text-sm font-semibold text-white"
                style={{
                  background:
                    cont.status === "active" ? "var(--good)" : cont.status === "degraded" ? "var(--warn)" : "var(--muted)",
                }}
              >
                session {cont.status}
              </span>
              <span className="text-sm text-[var(--muted)]">
                {cont.chunk_count} chunks · rolling score {cont.ema_score?.toFixed(3) ?? "–"}
              </span>
            </div>
            {history.length > 1 && (
              <svg viewBox="0 0 300 60" className="h-16 w-full" aria-label="rolling match score">
                <line x1="0" x2="300" y1={60 - acceptAt * 60} y2={60 - acceptAt * 60} stroke="var(--good)" strokeDasharray="4 4" />
                <polyline
                  fill="none"
                  stroke="var(--brand)"
                  strokeWidth="2"
                  points={history.map((v, i) => `${(i / (history.length - 1)) * 300},${60 - Math.max(0, v) * 60}`).join(" ")}
                />
              </svg>
            )}
          </div>
        )}
      </Card>

      {result && (
        <Card title="Result">
          <div className="mb-4 flex items-center gap-4">
            <DecisionBadge decision={result.decision} />
            <span className="text-sm text-[var(--muted)]">
              {result.decision === "STEP_UP" && "Route to iris or second-factor verification."}
              {result.decision === "ACCEPT" && "Voice matches the enrolled template."}
              {result.decision === "REJECT" && "Do not proceed with this action."}
            </span>
          </div>
          <ScoreBar label="Speaker match (cosine)" value={result.match_score} min={-0.2} max={1} marks={matchMarks} />
          <ScoreBar label={`Spoof likelihood (${result.spoof_model})`} value={result.spoof_score} marks={spoofMarks} invert />
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
            {result.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <div className="mt-3">
            <QualityLine q={result.quality} />
          </div>
          {result.decision === "STEP_UP" && (
            <div className="mt-4 rounded-[6px] border border-[var(--warning)] bg-[var(--warning-soft)] p-3">
              <p className="text-sm">A second factor is required before this action can proceed.</p>
              <Link
                href={`/iris?mode=verify&customer=${result.customer_id}&resolves=${result.event_id}${result.context ? `&context=${result.context}` : ""}`}
                className="mt-2 inline-flex h-10 items-center rounded-[6px] bg-[var(--brand)] px-4 text-sm font-medium text-white hover:bg-[var(--brand-strong)]"
              >
                Complete iris step-up
              </Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
