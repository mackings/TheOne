import type { LucideIcon } from "lucide-react";
import { cx } from "@/presentation/cx";
import { type RiskBand, riskBand } from "@/domain/network";

export type Tone = "neutral" | "good" | "warning" | "serious" | "critical" | "info" | "brand";

export const TONE: Record<Tone, { bg: string; dot: string }> = {
  neutral: { bg: "var(--surface-2)", dot: "var(--muted)" },
  good: { bg: "var(--good-soft)", dot: "var(--good)" },
  warning: { bg: "var(--warning-soft)", dot: "var(--warning)" },
  serious: { bg: "var(--serious-soft)", dot: "var(--serious)" },
  critical: { bg: "var(--critical-soft)", dot: "var(--critical)" },
  info: { bg: "var(--info-soft)", dot: "var(--info)" },
  brand: { bg: "var(--brand-soft)", dot: "var(--brand)" },
};

/** Status chip: tinted background, ink text, coloured dot or icon. Never colour alone. */
export function Badge({ tone = "neutral", icon: Icon, children, className }: { tone?: Tone; icon?: LucideIcon; children: React.ReactNode; className?: string }) {
  const t = TONE[tone];
  return (
    <span
      className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium text-[var(--ink)]", className)}
      style={{ background: t.bg }}
    >
      {Icon ? <Icon className="size-3.5" style={{ color: t.dot }} /> : <span className="size-1.5 rounded-full" style={{ background: t.dot }} />}
      {children}
    </span>
  );
}

const BAND: Record<RiskBand, { label: string; tone: Tone; bars: number }> = {
  very_high: { label: "Very high", tone: "critical", bars: 4 },
  high: { label: "High", tone: "serious", bars: 3 },
  medium: { label: "Medium", tone: "warning", bars: 2 },
  low: { label: "Low", tone: "neutral", bars: 1 },
};

/** Risk in words: Very high, High, Medium or Low. */
export function riskLevel(value: number): { label: string; tone: Tone; bars: number } {
  return BAND[riskBand(value)];
}

/** Risk as a word with a four-step bar. The exact score is in the tooltip. */
export function RiskScore({ value }: { value: number }) {
  const r = riskLevel(value);
  return (
    <span className="inline-flex items-center gap-2" title={`Risk score ${Math.round(value * 100)} out of 100`}>
      <span className="inline-flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className="w-[5px] rounded-[1px]" style={{ height: 4 + i * 3, background: i <= r.bars ? TONE[r.tone].dot : "var(--line-strong)" }} />
        ))}
      </span>
      <span className="text-sm font-medium">{r.label}</span>
    </span>
  );
}
