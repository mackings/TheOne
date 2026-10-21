"use client";

import { AlertTriangle, XCircle } from "lucide-react";

import { Badge, Button as KitButton, Section } from "@/presentation/components/ui";
import { DECISION, pick } from "@/presentation/status";
import type { Decision, Quality } from "@/domain/identity";

/** Flat, full-width panel used by the biometric pages. */
export function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <Section title={title} className={className}>
      {children}
    </Section>
  );
}

export function Button({
  variant = "primary",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  return <KitButton variant={variant} {...rest} />;
}

export function ScoreBar({
  label,
  value,
  min = 0,
  max = 1,
  marks = [],
  invert = false,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  marks?: { at: number; label: string }[];
  invert?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  // Colour by the policy marks when given: below the first mark is one band, above the last is the other.
  const sorted = [...marks].map((m) => m.at).sort((a, b) => a - b);
  const lo = sorted[0] ?? (invert ? 0.6 : 0.4);
  const hi = sorted[sorted.length - 1] ?? (invert ? 0.9 : 0.55);
  const good = invert ? value < lo : value >= hi;
  const mid = invert ? value < hi : value >= lo;
  const color = good ? "var(--good)" : mid ? "var(--warning)" : "var(--critical)";
  const band = good ? "Within policy" : mid ? "Borderline" : "Outside policy";
  return (
    <div className="mb-4">
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{label}</span>
        <span className="flex items-center gap-2">
          <span className="text-xs text-[var(--muted)]">{band}</span>
          <span className="font-mono tabular-nums">{value.toFixed(3)}</span>
        </span>
      </div>
      <div className="relative h-2 w-full rounded-full bg-[var(--track)]">
        <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
        {marks.map((m) => (
          <div
            key={m.label}
            title={`${m.label} ${m.at.toFixed(2)}`}
            className="absolute top-[-4px] h-4 w-[2px] bg-[var(--ink)]"
            style={{ left: `${((m.at - min) / (max - min)) * 100}%` }}
          />
        ))}
      </div>
      {marks.length > 0 && <div className="mt-1 text-xs text-[var(--muted)]">{marks.map((m) => `${m.label} ${m.at.toFixed(2)}`).join(" · ")}</div>}
    </div>
  );
}

export function DecisionBadge({ decision }: { decision: Decision | null | undefined }) {
  if (!decision) return null;
  const d = pick(DECISION, decision);
  return (
    <Badge tone={d.tone} icon={d.icon} className="px-3 py-1 text-sm">
      {decision === "STEP_UP" ? "Step-up required" : d.label}
    </Badge>
  );
}

export function LevelMeter({ level }: { level: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-[var(--track)]" role="meter" aria-label="Microphone level" aria-valuenow={Math.round(level * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-2 rounded-full bg-[var(--brand)] transition-[width] duration-75" style={{ width: `${level * 100}%` }} />
    </div>
  );
}

export function QualityLine({ q }: { q: Quality }) {
  return (
    <p className="text-xs text-[var(--muted)]">
      {q.duration_s}s · level {q.rms_dbfs} dBFS · speech {Math.round(q.speech_ratio * 100)}% · SNR {q.snr_db} dB
      {q.clipped && " · clipped"}
    </p>
  );
}

export function ErrorText({ error }: { error: string | null }) {
  return error ? (
    <div className="mt-3 flex items-start gap-2 rounded-[6px] border border-[var(--critical)] bg-[var(--critical-soft)] px-3 py-2 text-sm" role="alert">
      <XCircle className="mt-0.5 size-4 shrink-0 text-[var(--critical)]" />
      <span>{error}</span>
    </div>
  ) : null;
}

export function Notice({ children, tone = "warning" }: { children: React.ReactNode; tone?: "warning" | "info" }) {
  return (
    <div
      className="flex items-start gap-2 rounded-[6px] border px-3 py-2 text-sm"
      style={{ borderColor: tone === "warning" ? "var(--warning)" : "var(--info)", background: tone === "warning" ? "var(--warning-soft)" : "var(--info-soft)" }}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" style={{ color: tone === "warning" ? "var(--warn)" : "var(--info)" }} />
      <div>{children}</div>
    </div>
  );
}
