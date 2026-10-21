import type { RingNode } from "@/domain/network";
/** Labels and confirmation copy shared by the ring page's parts. */

export const ROLE: Record<string, string> = {
  collector: "First to receive",
  layer: "Passes it on",
  cash_out: "Takes it out",
  victim: "Possible victim",
  source: "Source",
  cash_point: "Cash point",
  exit: "Other bank",
  traced: "Found at other banks",
};

export type Act = { action: "watchlist_24h" | "confirm" | "dismiss" | "release"; accounts?: string[] } | null;

export const ACT_COPY: Record<string, { title: string; message: string; label: string; danger?: boolean; require?: string }> = {
  watchlist_24h: {
    title: "Watch these accounts for 24 hours?",
    message: "Money cannot leave these accounts for 24 hours: payments out are held and the bank freezes the balance. Everything returns to normal on its own after 24 hours.",
    label: "Watch for 24 hours",
  },
  confirm: {
    title: "Confirm these are mule accounts?",
    message: "Every account in the ring is marked as a mule, and the bank blocks all money going out of the ones held with us. Only the bank can lift that block later.",
    label: "Confirm ring",
    danger: true,
    require: "CONFIRM",
  },
  dismiss: {
    title: "Mark this ring as genuine?",
    message: "The accounts are cleared, any holds are lifted at the bank, and TheOne stops flagging them. It also learns from your decision.",
    label: "Not a mule ring",
  },
  release: {
    title: "Stop watching this account?",
    message: "Payments from this account go through normally again, and the bank lifts its hold.",
    label: "Release",
  },
};

export type Finding = { code: string; max: number; hits: { node: RingNode; reason: string }[] };

/** Every signal on the ring's members, grouped by rule, strongest first. */
export function findingsOf(members: RingNode[]): Finding[] {
  const by = new Map<string, Finding>();
  for (const n of members)
    for (const sg of n.signals) {
      const f = by.get(sg.code) ?? { code: sg.code, max: 0, hits: [] };
      f.max = Math.max(f.max, sg.weight);
      f.hits.push({ node: n, reason: sg.reason });
      by.set(sg.code, f);
    }
  return [...by.values()].sort((a, b) => b.max - a.max || b.hits.length - a.hits.length);
}
