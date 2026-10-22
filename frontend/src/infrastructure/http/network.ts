import type { NetworkGateway } from "@/application/ports";
import type {
  AccountBrief,
  AccountDetail,
  Backtest,
  BankAction,
  Evaluation,
  ImportJob,
  ImportResult,
  LearningRow,
  NetAlert,
  NetDecision,
  NetSignal,
  NetSummary,
  RingDetail,
  RingListItem,
  RiskModel,
  SafeLimit,
  StatementReport,
  TraceResult,
  TraceRow,
} from "@/domain/network";

import { API_KEY, API_URL, json, request } from "./client";

export const httpNetwork: NetworkGateway = {
  summary: () => request<NetSummary>("/network/summary"),
  analyse: () => request<NetSummary>("/network/analyse", { method: "POST" }),
  rings: () => request<RingListItem[]>("/network/rings"),
  ring: (id: string) => request<RingDetail>(`/network/rings/${id}`),
  ringAction: (id: string, action: string, actor: string, account_ids?: string[], note?: string) =>
    request<{ ring_id: string; action: string; accounts: string[]; ring_status: string }>(
      `/network/rings/${id}/actions`,
      json({ action, actor, account_ids, note }),
    ),
  evaluation: () => request<Evaluation>("/network/evaluation"),
  simulate: (seed: number, customers: number, rings: number) =>
    request<{ generated: Record<string, number>; summary: NetSummary; evaluation: Evaluation }>(
      "/network/simulate",
      json({ seed, customers, rings, reset: true }),
    ),
  search: (q: string) => request<AccountBrief[]>(`/network/accounts/search?q=${encodeURIComponent(q)}`),
  flagged: () => request<(AccountBrief & { signals: NetSignal[] })[]>("/network/accounts?flagged=true&limit=200"),
  decide: (source: AccountBrief, beneficiary: AccountBrief, amount_kobo: number) =>
    request<NetDecision>(
      "/network/decide",
      json({
        source: { bank_code: source.bank_code, account_no: source.account_no },
        beneficiary: { bank_code: beneficiary.bank_code, account_no: beneficiary.account_no },
        amount_kobo,
      }),
    ),
  decisions: (limit = 20) => request<NetDecision[]>(`/network/decisions?limit=${limit}`),
  simulateMulePayment: (bank_code: string, account_no: string, account_name: string, amount_kobo: number) =>
    request<NetDecision>("/network/simulate/mule-payment", json({ bank_code, account_no, account_name, amount_kobo })),
  reviewDecision: (id: string, outcome: "release" | "block", actor: string, note?: string) =>
    request<NetDecision>(`/network/decisions/${id}/review`, json({ outcome, actor, note })),
  accounts: (flagged: boolean, limit = 1000) =>
    request<(AccountBrief & { signals: NetSignal[] })[]>(`/network/accounts?flagged=${flagged}&limit=${limit}`),
  account: (id: string) => request<AccountDetail>(`/network/accounts/${id}`),
  syncAccount: (id: string) => request<{ daily_limit_kobo: number | null; kyc_tier: number | null; bank_status: string | null }>(`/network/accounts/${id}/sync`, { method: "POST" }),
  safeLimit: (id: string) => request<SafeLimit>(`/network/accounts/${id}/safe-limit`),
  setSafeLimit: (id: string, limit_kobo: number) => request<SafeLimit>(`/network/accounts/${id}/safe-limit`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit_kobo }) }),
  linkCustomer: (accountId: string, customer_id: string) => request<{ account_id: string }>(`/network/accounts/${accountId}/link`, json({ customer_id })),
  allAlerts: () => request<NetAlert[]>("/network/alerts?open_only=false&limit=500"),
  alerts: () => request<NetAlert[]>("/network/alerts"),
  importFile: (fmt: string, file: File, opts: { mapping?: string; bank_code?: string; account_no?: string; dry_run: boolean }) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.mapping) fd.append("mapping", opts.mapping);
    if (opts.bank_code) fd.append("bank_code", opts.bank_code);
    if (opts.account_no) fd.append("account_no", opts.account_no);
    fd.append("dry_run", String(opts.dry_run));
    return request<ImportResult>(`/network/import/${fmt}`, { method: "POST", body: fd });
  },
  /** Large NIP/CSV files: upload with progress, then the server imports in the background. */
  startImportJob: (fmt: string, file: File, opts: { mapping?: string; bank_code?: string; dry_run: boolean }, onUpload: (fraction: number) => void) =>
    new Promise<ImportJob>((resolve, reject) => {
      const fd = new FormData();
      fd.append("file", file);
      if (opts.mapping) fd.append("mapping", opts.mapping);
      if (opts.bank_code) fd.append("bank_code", opts.bank_code);
      fd.append("dry_run", String(opts.dry_run));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_URL}/network/import/${fmt}/job`);
      if (API_KEY) xhr.setRequestHeader("X-API-Key", API_KEY);
      xhr.upload.onprogress = (e) => e.lengthComputable && onUpload(e.loaded / e.total);
      xhr.onload = () => {
        let body: { detail?: unknown } & ImportJob;
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          return reject(new Error(xhr.statusText || "upload failed"));
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new Error(typeof body.detail === "string" ? body.detail : xhr.statusText));
      };
      xhr.onerror = () => reject(new Error("the upload was interrupted"));
      xhr.send(fd);
    }),
  importJob: (id: string) => request<ImportJob>(`/network/import/jobs/${id}`),
  bankActions: () => request<BankAction[]>("/network/bank-actions?limit=50"),
  retryBankAction: (id: string) => request<BankAction>(`/network/bank-actions/${id}/retry`, { method: "POST" }),
  backtest: (days: number, step_hours: number, capacity_per_day: number) =>
    request<Backtest>("/network/backtest", json({ days, step_hours, capacity_per_day })),
  learning: () =>
    request<{ enabled: boolean; min_samples: number; applied: Record<string, { learned: number; prior: number; multiplier: number; capped: boolean }>; candidates: LearningRow[] }>(
      "/network/learning",
    ),
  traceRing: (id: string, actor: string) =>
    request<TraceResult>(`/network/rings/${id}/trace`, json({ actor })),
  ringTraces: (id: string) => request<TraceRow[]>(`/network/rings/${id}/traces`),
  model: () => request<RiskModel>("/network/model"),
  trainModel: () => request<RiskModel>("/network/model/train", { method: "POST" }),
  refreshLearning: () => request<{ updated: LearningRow[]; skipped_low_samples: string[] }>("/network/learning/refresh", { method: "POST" }),
  checkStatement: (text: string) => request<StatementReport>("/network/statement/check", json({ text })),
  checkStatementFile: (file: File, password?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (password) fd.append("password", password);
    return request<StatementReport & { text: string }>("/network/statement/check-file", { method: "POST", body: fd });
  },
  importStatement: (text: string, bank_code: string) =>
    request<{ transfers_added: number; transfers_skipped: number; counterparties: number; with_account_number: number; account_id: string | null; risk_now: number | null; ring: string | null }>(
      "/network/statement/import", json({ text, bank_code })),
  labelsSummary: () => request<{ total: number; by_label: Record<string, Record<string, number>> }>("/network/labels/summary"),
  ackAlert: (id: string, actor: string) => request<NetAlert>(`/network/alerts/${id}/ack`, json({ actor })),
};
