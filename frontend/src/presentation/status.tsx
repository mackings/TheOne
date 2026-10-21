import {
  AlertOctagon,
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDot,
  Clock,
  Eye,
  Fingerprint,
  Hand,
  Info,
  type LucideIcon,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { Tone } from "@/presentation/components/ui";

type S = { tone: Tone; label: string; icon: LucideIcon };

export const DECISION: Record<string, S> = {
  ALLOW: { tone: "good", label: "Allowed", icon: CheckCircle2 },
  WARN_PAYEE: { tone: "warning", label: "Sender warned", icon: AlertTriangle },
  STEP_UP_OWNER: { tone: "serious", label: "Owner asked to confirm", icon: Fingerprint },
  HOLD: { tone: "critical", label: "Held", icon: Hand },
  STEP_UP: { tone: "serious", label: "Extra check needed", icon: Fingerprint },
  ACCEPT: { tone: "good", label: "Accepted", icon: CheckCircle2 },
  REJECT: { tone: "critical", label: "Rejected", icon: XCircle },
};

export const DECISION_STATUS: Record<string, S> = {
  allowed: { tone: "good", label: "Sent", icon: CheckCircle2 },
  released: { tone: "good", label: "Released", icon: CheckCircle2 },
  pending: { tone: "warning", label: "Awaiting customer", icon: Clock },
  pending_review: { tone: "serious", label: "Needs review", icon: Eye },
  blocked: { tone: "critical", label: "Blocked", icon: Ban },
  duress_hold: { tone: "critical", label: "Held quietly: customer in danger", icon: ShieldAlert },
};

export const RING_STATUS: Record<string, S> = {
  open: { tone: "info", label: "Open", icon: CircleDot },
  confirmed: { tone: "critical", label: "Confirmed", icon: ShieldAlert },
  dismissed: { tone: "neutral", label: "Dismissed", icon: XCircle },
  stale: { tone: "neutral", label: "No longer active", icon: Clock },
};

export const ACCOUNT_STATUS: Record<string, S> = {
  active: { tone: "neutral", label: "No restrictions", icon: CircleDot },
  watchlist: { tone: "warning", label: "On 24-hour watch", icon: Clock },
  confirmed_mule: { tone: "critical", label: "Confirmed mule", icon: ShieldAlert },
  cleared: { tone: "good", label: "Cleared", icon: ShieldCheck },
};

export const BANK_STATUS: Record<string, S> = {
  done: { tone: "good", label: "Done by the bank", icon: CheckCircle2 },
  failed: { tone: "critical", label: "Failed", icon: XCircle },
  shadow: { tone: "warning", label: "Not sent (test mode)", icon: Eye },
  recorded: { tone: "neutral", label: "To be done by hand", icon: Info },
  pending: { tone: "info", label: "Pending", icon: Clock },
};

export const SEVERITY: Record<string, S> = {
  critical: { tone: "critical", label: "Critical", icon: AlertOctagon },
  high: { tone: "serious", label: "High", icon: AlertTriangle },
  medium: { tone: "warning", label: "Medium", icon: AlertTriangle },
  low: { tone: "info", label: "Low", icon: Info },
};

export const ALERT_KIND: Record<string, string> = {
  duress: "Customer signalled danger",
  safe_limit: "Above the customer's own limit",
  review_cap: "Very large payment",
};

export const TYPOLOGY: Record<string, string> = {
  FAN_IN: "Money from many new people",
  PASS_THROUGH: "Money passes straight through",
  SPLIT_ROUND: "Split into round amounts",
  CASH_OUT: "Quickly withdrawn as cash",
  NEW_ACCOUNT_VELOCITY: "New account, high value",
  LOW_KYC_HIGH_VALUE: "Basic account, large amounts",
  DORMANT_REACTIVATED: "Unused account suddenly busy",
  DEVICE_FARM: "One phone, many new accounts",
  SHARED_IDENTIFIER: "Shares a phone or ID with others",
  VICTIM_COMPLAINT: "Named in a fraud complaint",
  CONFIRMED_MULE: "Confirmed mule",
  BVN_WATCHLIST: "Owner on the fraud watch-list",
  FAST_FROM_FLAGGED: "Got money from a suspicious account",
  LIVE_PASS_THROUGH: "Emptying new deposits right now",
  STATUS_CONFIRMED: "Confirmed by our team",
  STATUS_CLEARED: "Cleared by our team",
  REVIEW_CAP: "Very large single payment",
  AMOUNT_ANOMALY: "Far larger than usual",
  THIN_FILE_HIGH_VALUE: "Large amount, little history",
  NEW_PAYEE_HIGH_VALUE: "First payment to this person",
  DAILY_VELOCITY: "Unusual total for one day",
  KYC_TIER_LIMIT: "Above the daily limit",
  RAPID_DRAIN: "Several payments in minutes",
  NIGHT_HIGH_VALUE: "Large payment late at night",
  NEW_DEVICE_HIGH_VALUE: "Large payment from a new phone",
  LOCATION_ANOMALY: "Far from the usual place",
};

export function pick(map: Record<string, S>, key: string | null | undefined): S {
  return (key && map[key]) || { tone: "neutral", label: key ?? "–", icon: CircleDot };
}

/** How a payment was made, in everyday words. */
export const CHANNEL: Record<string, string> = {
  nip: "bank transfer", mobile: "mobile app", ussd: "USSD", internet: "internet banking", card: "card", pos: "POS",
  atm: "ATM", agent: "POS agent", branch: "branch", statement: "from a statement", statement_cash: "cash, from a statement",
};

/** Identity check level (CBN KYC tiers) in plain words. */
export const KYC_TIER: Record<number, string> = { 1: "Basic (tier 1)", 2: "Standard (tier 2)", 3: "Full (tier 3)" };
