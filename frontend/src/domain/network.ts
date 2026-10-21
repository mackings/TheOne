/** The mule network as the console sees it: accounts, rings, decisions, alerts, imports and learning. */

export type NetSignal = { code: string; weight: number; reason: string; evidence: Record<string, unknown> };

export type AccountBrief = {
  id: string;
  name: string;
  bank_code: string;
  account_no: string;
  home: boolean;
  status: string;
  risk: number;
  ring_id: string | null;
  ring_number?: number | null;
};

export type NetSummary = {
  computed_at: string;
  duration_ms: number;
  accounts: number;
  home_accounts: number;
  transfers_in_window: number;
  window_days: number;
  flagged_accounts: number;
  open_rings: number;
  confirmed_rings: number;
  rings: number;
  thresholds: { flag: number; hold: number; ring_min: number; fast_window_min: number };
  home_bank: { code: string; name: string };
  simulation_enabled: boolean;
  has_synthetic_labels: boolean;
  stale: boolean;
  mode: "enforce" | "shadow";
  bank_connector: string;
  nibss_connector: string;
  analysis_mode: "full" | "incremental";
  learning_enabled: boolean;
  learned_rules: number;
};

export type ImportResult = {
  format: string;
  rows: number;
  valid: number;
  errors: { row: number; error: string }[];
  dry_run: boolean;
  transfers_added?: number;
  transfers_skipped?: number;
  accounts?: number;
  statement_lines_added?: number;
};

export type BankAction = {
  id: string;
  created_at: string;
  kind: string;
  account_id: string;
  ring_id: string | null;
  reference: string;
  status: string;
  attempts: number;
  connector: string;
  last_error: string | null;
  request: Record<string, unknown>;
};

export type Backtest = {
  window: { start: string; end: string; days: number; step_hours: number; checkpoints: number; capacity_per_day: number };
  labels: { mules: number; legit: number };
  alerts: number;
  alerts_per_day: number;
  already_flagged_at_start: number;
  lead_time_cases: number;
  recall: number | null;
  precision_labelled: number | null;
  flagged_unlabelled: number;
  legit_flagged: number;
  precision_at_capacity: number | null;
  caught_before_confirmation: number;
  median_lead_hours: number | null;
  missed_mules: number;
  typologies: Record<string, { mule: number; legit: number; unlabelled: number }>;
  series: { at: string; new_alerts: number; reviewed: number; mules_flagged_so_far: number }[];
  duration_s: number;
};

export type LearningRow = { code: string; mule: number; legit: number; prior: number; learned: number; active: boolean; multiplier: number | null; capped: boolean; exempt: boolean };

export type RingListItem = {
  id: string;
  number: number | null;
  status: string;
  score: number;
  size: number;
  possible_victims: number;
  victim_inflow: number;
  cash_out_total: number;
  typologies: Record<string, number>;
  first_seen: string | null;
  last_seen: string | null;
  top_connected: AccountBrief[];
};

export type RingNode = {
  id: string;
  name: string;
  bank_code: string;
  account_no: string;
  home: boolean;
  role: "victim" | "source" | "collector" | "layer" | "cash_out" | "cash_point" | "exit" | "traced";
  risk: number;
  status: string;
  signals: NetSignal[];
};

export type RingEdge = { src: string; dst: string; amount: number; count: number; channels: string[]; first: string; last: string };

export type RingDetail = {
  id: string;
  number: number | null;
  status: string;
  score: number;
  summary: {
    size: number;
    roles: Record<string, string>;
    top_connected: string[];
    possible_victims: number;
    victim_inflow: number;
    cash_out_total: number;
    exit_accounts: number;
    shared_identifiers: { kind: string; masked: string; accounts: number }[];
    typologies: Record<string, number>;
    first_seen: string | null;
    last_seen: string | null;
  };
  nodes: RingNode[];
  edges: RingEdge[];
  identifier_links: { kind: string; masked: string; accounts: string[] }[];
  actions: { at: string; actor: string; action: string; accounts: string[]; note: string | null }[];
};

export type Evaluation = {
  mules: number;
  flagged: number;
  true_positives: number;
  precision: number | null;
  recall: number | null;
  home_mule_recall: number;
  victims: number;
  victims_flagged: number;
  false_positives: { id: string; name: string; risk: number }[];
  planted_rings: number;
  planted_rings_found: number;
  detected_rings: number;
  ring_precision: number | null;
};

export type NetDecision = {
  id: string;
  reference: string | null;
  decision: "ALLOW" | "WARN_PAYEE" | "STEP_UP_OWNER" | "HOLD";
  status: string;
  source: { id: string; bank_code: string; account_no: string; name: string };
  beneficiary: { id: string; bank_code: string; account_no: string; name: string };
  amount_kobo: number;
  source_risk: number;
  beneficiary_risk: number;
  sender_risk: number;
  context: Record<string, unknown> | null;
  reasons: string[];
  step_up_methods: string[];
  customer_id: string | null;
  latency_ms: number;
  created_at: string;
  resolution_note: string | null;
  source_signals: NetSignal[];
  beneficiary_signals: NetSignal[];
  sender_signals: NetSignal[];
  analysis_age_s: number | null;
};

export type NetAlert = {
  id: string;
  created_at: string;
  kind: "duress" | "safe_limit" | "review_cap" | string;
  severity: string;
  customer_id: string | null;
  account_id: string | null;
  decision_id: string | null;
  event_id: string | null;
  message: string;
  acknowledged_by: string | null;
};

export type AccountDetail = AccountBrief & {
  is_merchant: boolean;
  kyc_tier: number | null;
  opened_at: string | null;
  customer_id: string | null;
  signals: NetSignal[];
  model: { score: number; because: string[] } | null;
  inbound_total: number;
  outbound_total: number;
  recent: { ts: string; direction: "in" | "out"; counterparty: AccountBrief; amount: number; channel: string; reference: string }[];
};

export type SafeLimit = { limit_kobo: number | null; pending_limit_kobo: number | null; pending_effective_at: string | null; note: string | null };

export type StatementCheck = { code: string; title: string; fired: boolean; weight: number; detail: string };

export type StatementPayment = { date: string; to: string; amount: number; score: number; outcome: string; reasons: string[]; self: boolean };

export type StatementReport = {
  account: { holder: string; account_no: string; period_stated: string; opening: number | null; closing: number | null };
  coverage: { first: string; last: string; lines: number; skipped: number; truncated: boolean; layout: string; account_numbers_found: number };
  totals: { in: number; out: number; fees: number; self_out: number; credits: number; debits: number; min_balance: number | null; max_balance: number | null };
  mule: { score: number; band: string; flagged: boolean; checks: StatementCheck[] };
  payments: StatementPayment[];
  top_payees: { name: string; count: number; total: number; bank: string }[];
  payers: { name: string; count: number; total: number; self: boolean }[];
  everyday: { bills_and_data: number; businesses_paid: number; people_paid: number; card_funding: number };
  summary: string[];
  limits: string[];
};

export type ModelEval = { auc: number | null; precision: number | null; recall: number; flagged: number; legit_flagged: number };

export type ModelDisagreement = { account_id: string; name: string; account_no: string; model: number; rules: number; because: string[] };

export type RiskModel = {
  trained: boolean;
  min_each?: number;
  has_labels?: boolean;
  trained_at?: string;
  labels?: { mule: number; legit: number; sources: Record<string, number> };
  evaluation?: { method: string; rules: ModelEval; model: ModelEval };
  top_features?: { feature: string; weight: number; direction: string }[];
  disagreements?: { accounts: number; agreement: number | null; model_only: ModelDisagreement[]; rules_only: ModelDisagreement[] };
};

export type TraceResult = {
  accounts_traced: number; transfers_added: number; new_accounts: number; amount_followed: number; cash_found: number;
  connector: string; ring_id: string; ring_size: number | null;
  requests: { bank_code: string; account_no: string; hop: number; status: string; onward: number; error: string | null }[];
};

export type TraceRow = { at: string; actor: string; bank_code: string; account_no: string; hop: number; status: string; error: string | null;
  amount_in: number; onward: number; amount_onward: number; connector: string };

export type ImportJob = {
  id: string; created_at: string; finished_at: string | null; format: string; filename: string; size_bytes: number; bytes_read: number;
  dry_run: boolean; status: "queued" | "reading" | "analysing" | "done" | "failed"; rows: number; valid: number; transfers_added: number;
  transfers_skipped: number; accounts_added: number; error_count: number; errors: { row: number | null; error: string }[];
  message: string | null; progress: number | null;
};

export type RingActionKind = "watchlist_24h" | "confirm" | "dismiss" | "release";
export type RingActionResult = { ring_id: string; action: string; accounts: string[]; ring_status: string };
export type SimulationResult = { generated: Record<string, number>; summary: NetSummary; evaluation: Evaluation };
export type FlaggedAccount = AccountBrief & { signals: NetSignal[] };
export type BankSync = { daily_limit_kobo: number | null; kyc_tier: number | null; bank_status: string | null };
export type ImportOptions = { mapping?: string; bank_code?: string; account_no?: string; dry_run: boolean };
export type StatementImport = {
  transfers_added: number;
  transfers_skipped: number;
  counterparties: number;
  with_account_number: number;
  account_id: string | null;
  risk_now: number | null;
  ring: string | null;
};
export type LearningView = {
  enabled: boolean;
  min_samples: number;
  applied: Record<string, { learned: number; prior: number; multiplier: number; capped: boolean }>;
  candidates: LearningRow[];
};
export type LearningRefresh = { updated: LearningRow[]; skipped_low_samples: string[] };
export type LabelsSummary = { total: number; by_label: Record<string, Record<string, number>> };

export type RiskBand = "very_high" | "high" | "medium" | "low";

/** The engine flags an account at 0.60 and holds payments at 0.85. */
export const FLAG_AT = 0.6;
export const HOLD_AT = 0.85;

export function riskBand(score: number): RiskBand {
  if (score >= HOLD_AT) return "very_high";
  if (score >= FLAG_AT) return "high";
  if (score >= 0.35) return "medium";
  return "low";
}
