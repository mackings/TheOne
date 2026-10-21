"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Recorder } from "@/infrastructure/media/recorder";
import { Button, Card, ErrorText, LevelMeter, QualityLine } from "./parts";
import type { CompleteResult, EnrolmentSession, Sample } from "@/domain/identity";
import { useIdentity } from "@/presentation/hooks/gateways";

type Stage = "form" | "record" | "done";

export function EnrolPage() {
  const api = useIdentity();
  const [stage, setStage] = useState<Stage>("form");
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);
  const [name, setName] = useState("");
  const [externalId, setExternalId] = useState("");
  const [language, setLanguage] = useState("en");
  const [session, setSession] = useState<EnrolmentSession | null>(null);
  const [lastSample, setLastSample] = useState<Sample | null>(null);
  const [result, setResult] = useState<CompleteResult | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Recorder | null>(null);
  const raf = useRef<number>(0);
  const startedAt = useRef<number>(0);

  useEffect(() => {
    api.languages().then(setLanguages).catch((e) => setError(e.message));
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

  async function begin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const customer = await api.createCustomer({
        display_name: name.trim(),
        language,
        external_id: externalId.trim() || undefined,
      });
      const s = await api.createSession(customer.id, language);
      setSession(s);
      setStage("record");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    setError(null);
    setLastSample(null);
    try {
      rec.current = new Recorder();
      await rec.current.start();
      startedAt.current = Date.now();
      setRecording(true);
    } catch (err) {
      setError(`Microphone unavailable: ${(err as Error).message}`);
    }
  }

  async function stopRecording() {
    if (!rec.current || !session || session.next_step === null) return;
    setRecording(false);
    setBusy(true);
    try {
      const blob = await rec.current.stop();
      const sample = await api.uploadSample(session.id, session.next_step, blob);
      setLastSample(sample);
      const refreshed = await api.getSession(session.id);
      setSession(refreshed);
      if (refreshed.next_step === null) {
        const done = await api.completeSession(session.id);
        setResult(done);
        setStage("done");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (stage === "form") {
    return (
      <Card title="New customer">
        <form onSubmit={begin} className="grid max-w-md gap-4">
          <label className="grid gap-1 text-sm">
            Customer name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
              placeholder="Adaeze Okafor"
            />
          </label>
          <label className="grid gap-1 text-sm">
            Account or BVN reference (optional)
            <input
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
              placeholder="0123456789"
            />
          </label>
          <label className="grid gap-1 text-sm">
            Enrolment language
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? "Starting…" : "Start voice enrolment"}
          </Button>
          <ErrorText error={error} />
        </form>
      </Card>
    );
  }

  if (stage === "record" && session) {
    const step = session.next_step ?? 0;
    return (
      <div className="flex flex-col [&>:last-child]:mb-0 [&>:last-child]:flex-auto">
        <Card>
          <p className="text-[var(--muted)]">{session.guide.welcome}</p>
        </Card>
        <Card title={`Step ${step + 1} of ${session.required_samples}`}>
          <p className="mb-2 text-sm text-[var(--muted)]">{session.guide.step}</p>
          <p className="mb-6 text-2xl font-medium leading-snug">“{session.prompts[step]}”</p>

          {recording ? (
            <div className="grid gap-3">
              <LevelMeter level={level} />
              <div className="flex items-center gap-4">
                <Button variant="danger" onClick={stopRecording}>
                  Stop ({seconds.toFixed(1)}s)
                </Button>
                <span className="text-sm text-[var(--muted)]">Speak naturally, then press stop.</span>
              </div>
            </div>
          ) : (
            <Button onClick={startRecording} disabled={busy}>
              {busy ? "Processing…" : "Record"}
            </Button>
          )}
          <ErrorText error={error} />

          {lastSample && (
            <div
              className="mt-5 rounded-[6px] border px-4 py-3"
              style={{ borderColor: lastSample.accepted ? "var(--good)" : "var(--warn)" }}
            >
              <p className="font-medium">{lastSample.accepted ? "Sample accepted" : lastSample.message}</p>
              <QualityLine q={lastSample.quality} />
              {lastSample.spoof_score !== null && (
                <p className="text-xs text-[var(--muted)]">anti-spoof score {lastSample.spoof_score.toFixed(2)}</p>
              )}
            </div>
          )}
        </Card>
        <Card title="Progress">
          <div className="flex gap-2">
            {Array.from({ length: session.required_samples }).map((_, i) => (
              <div
                key={i}
                className="h-2 flex-1 rounded-full"
                style={{ background: i < session.accepted_samples ? "var(--good)" : "var(--track)" }}
              />
            ))}
          </div>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {session.accepted_samples} of {session.required_samples} samples accepted. Raw audio is discarded after the
            embedding is computed; only the encrypted template is stored.
          </p>
        </Card>
      </div>
    );
  }

  if (stage === "done" && result) {
    return (
      <Card title="Voice set up">
        <p className="text-lg">{result.message}</p>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <dt className="text-[var(--muted)]">Model</dt>
          <dd className="font-mono">{result.template.model_name}</dd>
          <dt className="text-[var(--muted)]">Samples</dt>
          <dd>{result.template.sample_count}</dd>
          <dt className="text-[var(--muted)]">Consistency</dt>
          <dd>{result.template.consistency.toFixed(3)}</dd>
        </dl>
        {result.warnings.map((w) => (
          <p key={w} className="mt-3 text-sm text-[var(--warn)]">
            {w}
          </p>
        ))}
        <div className="mt-5 flex gap-3">
          <Link
            href={`/verify?customer=${result.customer_id}`}
            className="inline-flex h-10 items-center rounded-[6px] bg-[var(--brand)] px-4 text-sm font-medium text-white hover:bg-[var(--brand-strong)]"
          >
            Verify this customer
          </Link>
          <Button variant="secondary" onClick={() => location.reload()}>
            Enrol another
          </Button>
        </div>
      </Card>
    );
  }

  return null;
}
