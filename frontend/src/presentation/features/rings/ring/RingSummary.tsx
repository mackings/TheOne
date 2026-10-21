"use client";

/** Summary tab: what happened step by step, the recommended next steps and the strongest evidence. */
import { ArrowDownToLine, Banknote, Check, Info, Landmark, Link2, type LucideIcon, MessageSquareWarning, Shuffle } from "lucide-react";
import { Badge, Button } from "@/presentation/components/ui";

import { naira } from "@/presentation/format";
import { actionPlan, plain, type PlanAction, type StoryKind, type StoryStep, strength } from "../explain";
import type { Finding } from "./copy";
import type { RingDetail } from "@/domain/network";

const STORY: Record<StoryKind, { icon: LucideIcon; bg: string; fg: string }> = {
  in: { icon: ArrowDownToLine, bg: "var(--info-soft)", fg: "var(--info)" },
  chain: { icon: Shuffle, bg: "var(--serious-soft)", fg: "var(--serious)" },
  cash: { icon: Banknote, bg: "var(--critical-soft)", fg: "var(--critical)" },
  banks: { icon: Landmark, bg: "var(--serious-soft)", fg: "var(--serious)" },
  linked: { icon: Link2, bg: "var(--warning-soft)", fg: "var(--warn)" },
  complaints: { icon: MessageSquareWarning, bg: "var(--critical-soft)", fg: "var(--critical)" },
};

export function RingSummary({ r, story, findings, onPlan, onSeeEvidence }: {
  r: RingDetail;
  story: StoryStep[];
  findings: Finding[];
  onPlan: (a?: PlanAction) => void;
  onSeeEvidence: () => void;
}) {
  return (
    <div className="grid border-b border-[var(--line)] bg-[var(--surface)] lg:grid-cols-[minmax(0,1fr)_420px] lg:divide-x lg:divide-[var(--line)]">
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <p className="text-sm text-[var(--muted)]">Step by step, worked out from the payments and the fraud complaints.</p>
        <ol className="relative mt-5">
          {story.map((step, i) => {
            const k = STORY[step.kind];
            return (
              <li key={step.title} className="relative flex gap-4 pb-6 last:pb-0">
                {i < story.length - 1 && <span className="absolute left-[17px] top-10 h-[calc(100%-36px)] w-px bg-[var(--line-strong)]" aria-hidden />}
                <span className="relative flex size-9 shrink-0 items-center justify-center rounded-full" style={{ background: k.bg }}>
                  <k.icon className="size-[18px]" style={{ color: k.fg }} />
                </span>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h3 className="text-sm font-semibold">{step.title}</h3>
                    <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 text-xs font-semibold tabular-nums text-[var(--ink)]">{step.figure}</span>
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--ink-2)]">{step.body}</p>
                  {step.detail && <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">{step.detail}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="grid content-start gap-6 border-t border-[var(--line)] px-4 py-6 sm:px-6 lg:border-t-0 lg:px-6">
        {(() => {
          const p = actionPlan(r);
          const c = { critical: ["var(--critical-soft)", "var(--critical)"], serious: ["var(--serious-soft)", "var(--serious)"], info: ["var(--info-soft)", "var(--info)"], good: ["var(--good-soft)", "var(--good)"] }[p.tone];
          return (
            <section className="overflow-hidden rounded-[8px] border border-[var(--line)]" aria-label="Recommended next steps">
              <div className="px-4 py-3.5" style={{ background: c[0] }}>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface)] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide" style={{ color: c[1] }}>
                  <span className="size-1.5 rounded-full" style={{ background: c[1] }} />
                  {p.urgency}
                </span>
                <h2 className="mt-2 text-base font-semibold leading-snug">{p.headline}</h2>
              </div>
              <ol className="divide-y divide-[var(--line)]">
                {p.steps.map((st, i) => (
                  <li key={st.text} className="flex gap-3 px-4 py-3.5">
                    <span
                      className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${st.done ? "bg-[var(--good)] text-white" : "border border-[var(--line-strong)] text-[var(--ink-2)]"}`}
                    >
                      {st.done ? <Check className="size-3.5" /> : i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm font-medium ${st.done ? "text-[var(--muted)] line-through decoration-[var(--line-strong)]" : ""}`}>{st.text}</div>
                      <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">{st.detail}</p>
                      {st.contacts && st.contacts.length > 0 && (
                        <ul className="mt-2 divide-y divide-[var(--line)] rounded-[6px] border border-[var(--line)]">
                          {st.contacts.map((ct) => (
                            <li key={ct.account + ct.name} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
                              <span className="min-w-0">
                                <span className="block truncate font-medium text-[var(--ink)]">{ct.name}</span>
                                <span className="font-mono text-[var(--muted)]">{ct.account}</span>
                              </span>
                              <span className="shrink-0 font-semibold tabular-nums">paid {naira(ct.amount)}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                      {st.action && !st.done && (
                        <Button size="sm" className="mt-2.5" variant={st.action === "confirm" || (st.action === "watchlist" && p.tone === "critical") ? "primary" : "secondary"}
                          disabled={st.action === "confirm" && r.status !== "open"} onClick={() => onPlan(st.action)}>
                          {st.label}
                        </Button>
                      )}
                      {st.done && <span className="mt-1 inline-block text-xs font-medium text-[var(--good)]">Done</span>}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          );
        })()}

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Strongest evidence</h2>
            <button className="text-sm font-medium text-[var(--brand)] hover:underline" onClick={onSeeEvidence}>See all {findings.length}</button>
          </div>
          <ul className="grid gap-1.5">
            {findings.slice(0, 3).map((f) => {
              const sg = strength(f.max);
              return (
                <li key={f.code} className="flex items-center justify-between gap-3 rounded-[6px] bg-[var(--surface-2)] px-3 py-2.5 text-sm">
                  <span className="min-w-0">{plain(f.code).title}</span>
                  <Badge tone={sg.tone}>{sg.label.replace(" evidence", "")}</Badge>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="flex items-start gap-1.5 text-xs text-[var(--muted)]">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          Scores show where to look. They are not proof of guilt, and the senders are treated as victims.
        </p>
      </div>
    </div>
  );
}
