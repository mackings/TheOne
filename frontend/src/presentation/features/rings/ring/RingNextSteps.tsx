"use client";

/** Next steps tab: what to do about the ring, as numbered steps with the button for each. */
import { Check } from "lucide-react";
import { Button } from "@/presentation/components/ui";

import { naira } from "@/presentation/format";
import { actionPlan, type PlanAction } from "../explain";
import type { RingDetail } from "@/domain/network";

const TONE = {
  critical: ["var(--critical-soft)", "var(--critical)"],
  serious: ["var(--serious-soft)", "var(--serious)"],
  info: ["var(--info-soft)", "var(--info)"],
  good: ["var(--good-soft)", "var(--good)"],
} as const;

export function RingNextSteps({ r, onPlan }: { r: RingDetail; onPlan: (a?: PlanAction) => void }) {
  const p = actionPlan(r);
  const [bg, fg] = TONE[p.tone];
  return (
    <div className="border-b border-[var(--line)] bg-[var(--surface)] px-4 py-6 sm:px-6 lg:px-8">
      <section className="max-w-3xl overflow-hidden rounded-[8px] border border-[var(--line)]" aria-label="Next steps">
        <div className="px-5 py-4" style={{ background: bg }}>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface)] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide" style={{ color: fg }}>
            <span className="size-1.5 rounded-full" style={{ background: fg }} />
            {p.urgency}
          </span>
          <h2 className="mt-2 text-lg font-semibold leading-snug">{p.headline}</h2>
        </div>
        <ol className="divide-y divide-[var(--line)]">
          {p.steps.map((st, i) => (
            <li key={st.text} className="flex gap-4 px-5 py-4">
              <span className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${st.done ? "bg-[var(--good)] text-white" : "border border-[var(--line-strong)] text-[var(--ink-2)]"}`}>
                {st.done ? <Check className="size-4" /> : i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className={`font-medium ${st.done ? "text-[var(--muted)] line-through decoration-[var(--line-strong)]" : ""}`}>{st.text}</div>
                <p className="mt-0.5 text-sm text-[var(--muted)]">{st.detail}</p>
                {st.contacts && st.contacts.length > 0 && (
                  <ul className="mt-3 max-w-lg divide-y divide-[var(--line)] rounded-[6px] border border-[var(--line)]">
                    {st.contacts.map((ct) => (
                      <li key={ct.account + ct.name} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{ct.name}</span>
                          <span className="text-xs text-[var(--muted)]">{ct.account}</span>
                        </span>
                        <span className="shrink-0 font-semibold tabular-nums">paid {naira(ct.amount)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {st.action && !st.done && (
                  <Button size="sm" className="mt-3" variant={st.action === "confirm" || (st.action === "watchlist" && p.tone === "critical") ? "primary" : "secondary"}
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
    </div>
  );
}
