"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";

export type MixPart = { key: string; label: string; value: number; color: string; icon?: LucideIcon };

/**
 * Part-to-whole for a handful of states: one 100% bar, segments separated by a 2px surface gap,
 * rounded only at the outer ends, a hover tooltip per segment, and a legend with counts so the
 * state is never carried by colour alone.
 */
export function MixBar({ parts, unit = "", ariaLabel }: { parts: MixPart[]; unit?: string; ariaLabel: string }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  const [hover, setHover] = useState<string | null>(null);
  const shown = parts.filter((p) => p.value > 0);
  return (
    <div>
      <div className="relative">
        <div className="flex h-7 w-full gap-[2px] overflow-hidden rounded-[4px]" role="img" aria-label={ariaLabel}>
          {total === 0 ? (
            <div className="flex h-full w-full items-center justify-center bg-[var(--surface-2)] text-xs text-[var(--muted)]">No {unit.trim() || "data"} recorded yet</div>
          ) : (
            shown.map((p) => (
              <div
                key={p.key}
                className="h-full transition-opacity"
                style={{ flexGrow: p.value, flexBasis: 0, background: p.color, opacity: hover && hover !== p.key ? 0.45 : 1, minWidth: 6 }}
                onMouseEnter={() => setHover(p.key)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(p.key)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={`${p.label}: ${p.value}${unit}`}
              />
            ))
          )}
        </div>
        {hover && total > 0 && (() => {
          const p = parts.find((x) => x.key === hover)!;
          return (
            <div className="pointer-events-none absolute -top-12 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-[6px] border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-xs shadow-md">
              <span className="font-semibold">{p.label}</span>
              <span className="text-[var(--muted)]">
                {" "}
                · {p.value.toLocaleString()}
                {unit} · {Math.round((p.value / total) * 100)}%
              </span>
            </div>
          );
        })()}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center gap-2" onMouseEnter={() => setHover(p.key)} onMouseLeave={() => setHover(null)}>
            <span className="size-2.5 rounded-[2px]" style={{ background: p.color }} />
            {p.icon && <p.icon className="size-3.5 text-[var(--muted)]" />}
            <span className="text-[var(--ink-2)]">{p.label}</span>
            <span className="font-semibold tabular-nums">{p.value.toLocaleString()}</span>
            <span className="text-xs tabular-nums text-[var(--muted)]">{total ? `${Math.round((p.value / total) * 100)}%` : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
