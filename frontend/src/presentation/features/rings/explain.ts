import { bankName, fmtDate, naira } from "@/presentation/format";
import type { RingDetail, RingNode } from "@/domain/network";

/** Plain-language meaning of each detection rule, written for a non-technical reader. */
export const PLAIN: Record<string, { title: string; means: string }> = {
  FAN_IN: {
    title: "Many unrelated people paid the same account",
    means: "Ordinary accounts are paid by a few familiar people. A mule account suddenly receives money from many strangers in a short time, which is what happens when several fraud victims are told to pay into it.",
  },
  PASS_THROUGH: {
    title: "Money was moved on almost as soon as it arrived",
    means: "The account kept almost nothing. Most of what came in left again within minutes or hours, so it acts as a pipe for someone else's money, not as a real customer's account.",
  },
  SPLIT_ROUND: {
    title: "Money was split into round amounts",
    means: "Large credits were quickly broken into round sums and sent to several accounts. Fraudsters do this to spread money across mules and stay under transfer limits.",
  },
  CASH_OUT: {
    title: "Money was withdrawn as cash quickly",
    means: "Funds were taken out through ATMs or POS agents soon after arriving. Once money is cash it cannot be recalled, which is why fraudsters do this fast.",
  },
  NEW_ACCOUNT_VELOCITY: {
    title: "A new account handled large sums",
    means: "The account is only days or weeks old but has already moved a lot of money. Mule accounts are often opened just for one scheme.",
  },
  LOW_KYC_HIGH_VALUE: {
    title: "Basic-level account moving large sums",
    means: "The account was opened with only the most basic identity checks, yet it handles amounts usually seen on fully verified accounts.",
  },
  DORMANT_REACTIVATED: {
    title: "A long-unused account suddenly became busy",
    means: "The account sat unused for months, then started moving money. Dormant accounts are sometimes sold or taken over for fraud.",
  },
  DEVICE_FARM: {
    title: "One phone runs several new accounts",
    means: "The same device logs into several recently opened accounts. This usually means one person controls them, sometimes through agent-assisted account opening.",
  },
  SHARED_IDENTIFIER: {
    title: "Accounts share a phone number, phone or BVN",
    means: "Accounts that look unrelated use the same phone number, the same phone, or the same BVN (the ID number every Nigerian bank customer has). That points to one person or group running them together.",
  },
  VICTIM_COMPLAINT: {
    title: "Fraud victims named this account",
    means: "Customers reported they were defrauded and gave this account as the one they paid. This is direct evidence, not a pattern.",
  },
  BVN_WATCHLIST: {
    title: "The account holder is on the fraud watch-list",
    means: "Nigerian banks share a watch-list of people already confirmed in fraud. This account holder is on it.",
  },
  CONFIRMED_MULE: {
    title: "Already confirmed as a mule",
    means: "Our fraud team or another bank has already confirmed this account as a mule.",
  },
  FAST_FROM_FLAGGED: {
    title: "Received money straight from a flagged account",
    means: "Money arrived from an account already flagged as a mule and was moved again shortly after. It is the next link in the chain.",
  },
  LIVE_PASS_THROUGH: {
    title: "Emptying new deposits right now",
    means: "Money that just arrived is already leaving. This is happening now, so acting quickly can still stop funds leaving.",
  },
  STATUS_CONFIRMED: { title: "Confirmed by our team", means: "Someone on the fraud team confirmed this account as a mule." },
  STATUS_CLEARED: { title: "Cleared by our team", means: "Someone on the fraud team checked this account and found it genuine." },
};

export const plain = (code: string) => PLAIN[code] ?? { title: code.replace(/_/g, " ").toLowerCase(), means: "" };

export const ROLE_PLAIN: Record<string, { label: string; means: string }> = {
  victim: { label: "Possible victim", means: "Paid money into the ring. Treated as a victim, never as a suspect." },
  source: { label: "Source", means: "Sent money into the ring." },
  collector: { label: "First to receive", means: "First account to receive the victims' money." },
  layer: { label: "Passes it on", means: "Receives money from the collectors and sends it on, to hide where it came from." },
  cash_out: { label: "Takes it out", means: "Last account in the chain. Withdraws the money as cash or sends it out." },
  cash_point: { label: "Cash point", means: "ATM or POS agent where money was withdrawn." },
  exit: { label: "Other bank", means: "Account at another bank where money went after leaving the ring." },
  traced: { label: "Found at other banks", means: "Account at another bank that received the money next, found by asking that bank." },
};

/** Describe how much a single finding counts, in words rather than a weight. */
export function strength(weight: number): { label: string; tone: "critical" | "serious" | "neutral" } {
  if (weight >= 0.5) return { label: "Strong evidence", tone: "critical" };
  if (weight >= 0.3) return { label: "Moderate evidence", tone: "serious" };
  return { label: "Supporting evidence", tone: "neutral" };
}

export function duration(ms: number) {
  const m = Math.max(1, Math.round(ms / 60000));
  if (m < 90) return `${m} minute${m > 1 ? "s" : ""}`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} hour${h > 1 ? "s" : ""}`;
  const d = Math.round(h / 24);
  return `${d} day${d > 1 ? "s" : ""}`;
}

const when = (iso: string | null | undefined) => (iso ? fmtDate(iso) : "");

export type StoryKind = "in" | "chain" | "cash" | "banks" | "linked" | "complaints";
export type StoryStep = { kind: StoryKind; title: string; figure: string; body: string; detail?: string };

/** ₦4.4m, ₦300k: short amounts for headline figures. */
export function shortNaira(kobo: number) {
  const n = kobo / 100;
  if (n >= 1e9) return `₦${(n / 1e9).toFixed(1)}bn`;
  if (n >= 1e6) return `₦${(n / 1e6).toFixed(1)}m`;
  if (n >= 1e3) return `₦${Math.round(n / 1e3)}k`;
  return `₦${Math.round(n)}`;
}

/** Turn a ring into a short, numbered story a branch manager or a court could follow. */
/** The ring without the payments TheOne stopped: they are drawn on the map, but that money never moved. */
const moved = (r: RingDetail): RingDetail => ({ ...r, edges: r.edges.filter((e) => !e.stopped) });

export function ringStory(ring: RingDetail): StoryStep[] {
  const r = moved(ring);
  const byId = new Map(r.nodes.map((n) => [n.id, n]));
  const role = (id: string) => byId.get(id)?.role;
  const isVictim = (id: string) => ["victim", "source"].includes(role(id) ?? "");
  const isExit = (id: string) => ["cash_point", "exit"].includes(role(id) ?? "");
  const inRing = (id: string) => !!r.summary.roles[id];
  const members = r.nodes.filter((n) => inRing(n.id));
  const named = (ids: string[]) => {
    const names = ids.map((id) => byId.get(id)?.name || "an account");
    return names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} and ${names.length - 2} other${names.length > 3 ? "s" : ""}`;
  };

  const inEdges = r.edges.filter((e) => isVictim(e.src) && inRing(e.dst));
  const receivers = [...new Set(inEdges.map((e) => e.dst))];
  const firstIn = inEdges.map((e) => e.first).sort()[0];
  const lastIn = inEdges.map((e) => e.last).sort().at(-1);
  const steps: StoryStep[] = [];

  steps.push({
    kind: "in",
    title: "Money came in from many people",
    figure: `${shortNaira(r.summary.victim_inflow)} from ${r.summary.possible_victims}`,
    body: `${r.summary.possible_victims} people sent ${naira(r.summary.victim_inflow)} to ${receivers.length} account${receivers.length === 1 ? "" : "s"} (${named(receivers)})${firstIn ? ` between ${when(firstIn)} and ${when(lastIn)}` : ""}.`,
    detail: "Most had never paid these accounts before, so they are treated as possible fraud victims.",
  });

  const onward = r.edges.filter((e) => inRing(e.src) && inRing(e.dst));
  const firstOut = r.edges.filter((e) => inRing(e.src)).map((e) => e.first).sort()[0];
  if (onward.length) {
    const passed = onward.filter((e) => receivers.includes(e.src)).reduce((a, e) => a + e.amount, 0);
    const layers = [...new Set(onward.map((e) => e.dst))].filter((id) => !receivers.includes(id));
    const gap = firstIn && firstOut ? new Date(firstOut).getTime() - new Date(firstIn).getTime() : null;
    steps.push({
      kind: "chain",
      title: "It was passed along a chain of accounts",
      figure: gap != null && gap >= 0 ? `within ${duration(gap)}` : `${layers.length} accounts`,
      body: `${gap != null && gap >= 0 ? `Within ${duration(gap)} of the first payment, ` : ""}${naira(passed)} was moved on to ${layers.length || "other"} account${layers.length === 1 ? "" : "s"}${layers.length ? ` (${named(layers)})` : ""}.`,
      detail: `${passed > r.summary.victim_inflow ? "That is more than the victims paid in, so these accounts also move money from other sources. " : ""}Passing money through several accounts makes it harder to trace and recover.`,
    });
  }

  const outEdges = r.edges.filter((e) => inRing(e.src) && isExit(e.dst));
  if (outEdges.length || r.summary.cash_out_total) {
    const points = [...new Set(outEdges.filter((e) => role(e.dst) === "cash_point").map((e) => e.dst))];
    const atm = points.filter((id) => /atm/i.test(byId.get(id)?.name ?? "")).length;
    const pos = points.length - atm;
    const share = r.summary.victim_inflow ? Math.round((r.summary.cash_out_total / r.summary.victim_inflow) * 100) : null;
    const via = [atm ? `${atm} ATM${atm > 1 ? "s" : ""}` : "", pos ? `${pos} POS agent${pos > 1 ? "s" : ""}` : ""].filter(Boolean).join(" and ");
    steps.push({
      kind: "cash",
      title: "Most of it was withdrawn as cash",
      figure: share != null ? `${Math.min(share, 100)}% as cash` : shortNaira(r.summary.cash_out_total),
      body: `${naira(r.summary.cash_out_total)}${share != null ? `, about ${Math.min(share, 100)}% of what the victims paid,` : ""} left as cash${via ? ` through ${via}` : ""}.`,
      detail: "Cash cannot be recalled, which is why mule rings withdraw quickly.",
    });
  }

  const traced = r.nodes.filter((n) => n.role === "traced");
  if (traced.length) {
    const exits = r.nodes.filter((n) => n.role === "exit");
    const sentOut = r.edges.filter((e) => inRing(e.src) && role(e.dst) === "exit").reduce((a, e) => a + e.amount, 0);
    const movedOn = r.edges.filter((e) => role(e.src) === "exit").reduce((a, e) => a + e.amount, 0);
    const banks = new Set(traced.map((n) => n.bank_code)).size;
    steps.push({
      kind: "banks",
      title: "It was followed into other banks",
      figure: `${traced.length} accounts · ${banks} banks`,
      body: `${naira(sentOut)} was sent to ${exits.length} account${exits.length === 1 ? "" : "s"} at other banks, and those banks say ${naira(movedOn)} of it moved on again to ${traced.length} more account${traced.length > 1 ? "s" : ""}.`,
      detail: "Those banks can be asked to hold what is left.",
    });
  }

  if (r.identifier_links.length) {
    const linked = new Set(r.identifier_links.flatMap((l) => l.accounts));
    const word: Record<string, string> = { bvn: "BVN", phone: "phone number", device: "device" };
    const kinds = [...new Set(r.identifier_links.map((l) => word[l.kind] ?? l.kind))].join(" or ");
    steps.push({
      kind: "linked",
      title: "The accounts are controlled together",
      figure: `${linked.size} of ${members.length} linked`,
      body: `${linked.size === members.length ? "All" : linked.size} of the ${members.length} accounts use the same ${kinds}.`,
      detail: "Accounts that look unrelated but share these details are usually run by one person or group.",
    });
  }

  const complaints = members.filter((n) => n.signals.some((s) => s.code === "VICTIM_COMPLAINT"));
  if (complaints.length) {
    const reports = complaints.reduce((a, n) => a + Number(n.signals.find((s) => s.code === "VICTIM_COMPLAINT")?.evidence?.complaints ?? 1), 0);
    steps.push({
      kind: "complaints",
      title: "Victims have already complained",
      figure: `${reports} report${reports === 1 ? "" : "s"}`,
      body: `Fraud reports name ${named(complaints.map((n) => n.id))} as the account${complaints.length > 1 ? "s" : ""} they were told to pay.`,
      detail: "This is direct evidence, not a pattern.",
    });
  }
  return steps;
}

export type PlanAction = "watchlist" | "confirm" | "evidence" | "trace" | "accounts";
export type PlanStep = { text: string; detail: string; action?: PlanAction; label?: string; done?: boolean;
  contacts?: { name: string; account: string; amount: number }[] };
export type Plan = { tone: "critical" | "serious" | "info" | "good"; urgency: string; headline: string; steps: PlanStep[] };

/** What to do next, as numbered steps with the button for each, worked out from the ring itself. */
export function actionPlan(ring: RingDetail): Plan {
  const r = moved(ring);
  const byId = new Map(r.nodes.map((n) => [n.id, n]));
  const members = r.nodes.filter((n) => r.summary.roles[n.id]);
  const ours = members.filter((n) => n.home);
  const watched = ours.length > 0 && ours.every((n) => n.status === "watchlist" || n.status === "confirmed_mule");
  const paid = new Map<string, number>();
  for (const e of r.edges) if (["victim", "source"].includes(byId.get(e.src)?.role ?? "") && r.summary.roles[e.dst]) paid.set(e.src, (paid.get(e.src) ?? 0) + e.amount);
  const contacts = [...paid.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([id, amount]) => {
    const n = byId.get(id)!;
    return { name: n.name || "Unknown", account: `…${n.account_no.slice(-4)} · ${n.home ? "our bank" : bankName(n.bank_code)}`, amount };
  });
  const otherBanks = r.nodes.some((n) => n.role === "exit" && !n.home);
  const traced = r.nodes.some((n) => n.role === "traced");
  const call: PlanStep = { text: "Call two or three of the people who paid in", detail: "Ask what they were paying for and whether they were pressured. Their answers decide the next step.", contacts };
  const trace: PlanStep = { text: "Ask the other banks to hold what is left", detail: "Money went to accounts at other banks. TheOne can ask those banks where it went next, so they can act too.", action: "trace", label: "Ask the banks", done: traced };
  const pack: PlanStep = { text: "Keep the evidence pack with the case file", detail: "A printable summary of the ring, the findings and the money trail.", action: "evidence", label: "Open evidence pack" };

  if (r.status === "confirmed")
    return { tone: "good", urgency: "Confirmed", headline: "Help the victims recover their money", steps: [
      { ...call, text: "Contact the people who paid in about recovery", detail: "Post-no-debit blocks were requested at the bank, so what is left in these accounts can be returned." },
      ...(otherBanks ? [trace] : []), pack] };
  if (r.status === "dismissed")
    return { tone: "info", urgency: "Closed", headline: "Marked as genuine", steps: [
      { text: "No action is needed", detail: "The ring reopens on its own if new activity appears." }] };
  const urgent = r.score >= 0.85 || members.some((n) => n.signals.some((s) => s.code === "VICTIM_COMPLAINT"));
  return {
    tone: urgent ? "critical" : "serious",
    urgency: urgent ? "Act today" : "Review today",
    headline: urgent ? "Stop the money, then confirm with the victims" : "Check before more money leaves",
    steps: ours.length
      ? [
          { text: `Stop money leaving the ${ours.length} account${ours.length === 1 ? "" : "s"} at our bank for 24 hours`,
            detail: "Payments out are held and the bank freezes the balance. Everything returns to normal on its own after 24 hours.",
            action: "watchlist", label: "Watch for 24 hours", done: watched },
          call,
          { text: "If they confirm the fraud, confirm the ring",
            detail: "This marks the accounts as mules and the bank blocks all money going out of them. A supervisor approves it.",
            action: "confirm", label: "Confirm the ring" },
          ...(otherBanks && !traced ? [trace] : []),
          pack,
        ]
      // None of the ring's accounts are at our bank, so only their own banks can freeze them.
      : [
          { text: "Ask the receiving banks to freeze these accounts",
            detail: "All the accounts in this ring are at other banks, so the hold has to be placed there. Send them the evidence pack.",
            action: "evidence", label: "Open evidence pack" },
          call,
          { text: "If they confirm the fraud, confirm the ring",
            detail: "This marks the accounts as mules, so any payment to them from our customers is held. A supervisor approves it.",
            action: "confirm", label: "Confirm the ring" },
        ],
  };
}

export const nodeLabel = (n: RingNode) => n.name || `${n.bank_code}/${n.account_no}`;
