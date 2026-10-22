"use client";

/** What happened tab: the ring's story in a few short steps, and any payments TheOne stopped on their way in. */
import { ArrowDownToLine, Banknote, Hand, Landmark, Link2, type LucideIcon, MessageSquareWarning, Shuffle } from "lucide-react";

import { naira } from "@/presentation/format";
import type { StoryKind, StoryStep } from "../explain";
import type { RingDetail } from "@/domain/network";

const STORY: Record<StoryKind, { icon: LucideIcon; bg: string; fg: string }> = {
  in: { icon: ArrowDownToLine, bg: "var(--info-soft)", fg: "var(--info)" },
  chain: { icon: Shuffle, bg: "var(--serious-soft)", fg: "var(--serious)" },
  cash: { icon: Banknote, bg: "var(--critical-soft)", fg: "var(--critical)" },
  banks: { icon: Landmark, bg: "var(--serious-soft)", fg: "var(--serious)" },
  linked: { icon: Link2, bg: "var(--warning-soft)", fg: "var(--warn)" },
  complaints: { icon: MessageSquareWarning, bg: "var(--critical-soft)", fg: "var(--critical)" },
};

export function RingSummary({ r, story }: { r: RingDetail; story: StoryStep[] }) {
  return (
    <div className="border-b border-[var(--line)] bg-[var(--surface)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="max-w-3xl">
        {r.stopped_payments.length > 0 && <Stopped r={r} />}
        <ol className="relative">
          {story.map((step, i) => {
            const k = STORY[step.kind];
            return (
              <li key={step.title} className="relative flex gap-4 pb-7 last:pb-0">
                {i < story.length - 1 && <span className="absolute left-[17px] top-10 h-[calc(100%-36px)] w-px bg-[var(--line-strong)]" aria-hidden />}
                <span className="relative flex size-9 shrink-0 items-center justify-center rounded-full" style={{ background: k.bg }}>
                  <k.icon className="size-[18px]" style={{ color: k.fg }} />
                </span>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h3 className="font-semibold">{step.title}</h3>
                    <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 text-xs font-semibold tabular-nums">{step.figure}</span>
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--ink-2)]">{step.body}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

/** Payments TheOne held on their way into this ring: money the ring never got. */
function Stopped({ r }: { r: RingDetail }) {
  const list = r.stopped_payments;
  const kept = list.reduce((n, p) => n + p.amount, 0);
  return (
    <div className="mb-7 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-[8px] bg-[var(--critical-soft)] px-4 py-3 text-sm">
      <span className="flex items-center gap-2 font-semibold text-[var(--critical)]">
        <Hand className="size-4" />
        {list.length === 1
          ? `TheOne stopped a payment from ${list[0].from.name} to this ring`
          : `TheOne stopped ${list.length} payments heading to this ring`}
      </span>
      <span className="font-semibold tabular-nums text-[var(--critical)]">{naira(kept)} kept safe</span>
    </div>
  );
}
