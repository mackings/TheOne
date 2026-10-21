"use client";

import { ArrowDownLeft, ArrowUpRight, RefreshCcw, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  Drawer,
  EmptyState,
  Field,
  FilterBar,
  InlineError,
  Input,
  PageHeader,
  RiskScore,
  SearchInput,
  Segmented,
  Select,
  useToast,
} from "@/presentation/components/ui";
import { accountLine, bankName, fmtDate, fmtDay, naira, ringName } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { ACCOUNT_STATUS, CHANNEL, KYC_TIER, pick, TYPOLOGY } from "@/presentation/status";
import type { AccountBrief, NetSignal } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

type Row = AccountBrief & { signals: NetSignal[] };
type Band = "all" | "high" | "elevated" | "watch";

export function AccountsPage() {
  const net = useNetwork();
  const toast = useToast();
  const list = useAsync(() => net.accounts(false), [], { every: 30_000 });
  const [band, setBand] = useState<Band>("elevated");
  const [status, setStatus] = useState("");
  const [bank, setBank] = useState("");
  const [typology, setTypology] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  const all = useMemo(() => list.data ?? [], [list.data]);
  const typologies = useMemo(() => Array.from(new Set(all.flatMap((a) => a.signals.map((s) => s.code)))).sort(), [all]);
  const inBand = (a: Row, b: Band) => (b === "all" ? true : b === "high" ? a.risk >= 0.85 : b === "elevated" ? a.risk >= 0.6 : a.risk >= 0.35 && a.risk < 0.6);
  const rows = all.filter(
    (a) =>
      inBand(a, band) &&
      (!status || a.status === status) &&
      (!bank || (bank === "home" ? a.home : !a.home)) &&
      (!typology || a.signals.some((s) => s.code === typology)) &&
      (!q || `${a.name} ${a.account_no} ${a.bank_code}`.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle="Every account TheOne has checked, the riskiest first, and why."
      />
      <InlineError error={list.error} onRetry={list.reload} />
      <FilterBar
        right={<span className="text-xs text-[var(--muted)]">{rows.length} accounts</span>}
        active={(status ? 1 : 0) + (bank ? 1 : 0) + (typology ? 1 : 0)}
        more={
          <>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Status"
              options={[{ value: "", label: "Any status" }, ...Object.entries(ACCOUNT_STATUS).map(([k, v]) => ({ value: k, label: v.label }))]} />
            <Select value={bank} onChange={(e) => setBank(e.target.value)} className="w-44" aria-label="Bank"
              options={[{ value: "", label: "Any bank" }, { value: "home", label: "Our customers" }, { value: "other", label: "Other banks" }]} />
            <Select value={typology} onChange={(e) => setTypology(e.target.value)} className="w-64" aria-label="Warning sign"
              options={[{ value: "", label: "Any warning sign" }, ...typologies.map((t) => ({ value: t, label: TYPOLOGY[t] ?? t }))]} />
          </>
        }
      >
        <Segmented<Band>
          value={band}
          onChange={setBand}
          options={[
            { value: "elevated", label: "Suspicious", count: all.filter((a) => inBand(a, "elevated")).length },
            { value: "high", label: "Very high risk", count: all.filter((a) => inBand(a, "high")).length },
            { value: "watch", label: "Medium risk", count: all.filter((a) => inBand(a, "watch")).length },
            { value: "all", label: "All", count: all.length },
          ]}
        />
        <SearchInput value={q} onChange={setQ} placeholder="Name or account number" className="w-full sm:w-56" />
      </FilterBar>
      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<Row>
          rows={rows}
          loading={list.loading}
          rowKey={(a) => a.id}
          onRowClick={(a) => setOpen(a.id)}
          selectedKey={open}
          initialSort={{ key: "risk", dir: "desc" }}
          empty={<EmptyState icon={Users} title="No accounts match" description="Choose “All” or clear a filter to see more." />}
          columns={[
            { key: "name", header: "Account", sort: (a) => a.name, render: (a) => <div><div className="font-medium">{a.name || "Unknown"}</div><div className="text-xs text-[var(--muted)]">{accountLine(a.account_no, a.bank_code, a.home)}</div></div> },
            { key: "risk", header: "Risk", sort: (a) => a.risk, render: (a) => <RiskScore value={a.risk} /> },
            { key: "why", header: "Main warning sign", hideBelow: "md", render: (a) => <span className="text-xs">{a.signals[0] ? TYPOLOGY[a.signals[0].code] ?? a.signals[0].code : "–"}</span> },
            { key: "ring", header: "Ring", hideBelow: "lg", render: (a) => (a.ring_id ? <Link className="text-sm hover:text-[var(--brand)] hover:underline" href={`/network/rings/${a.ring_id}`} onClick={(e) => e.stopPropagation()}>{ringName({ id: a.ring_id, number: a.ring_number })}</Link> : <span className="text-xs text-[var(--muted)]">–</span>) },
            { key: "status", header: "Status", sort: (a) => a.status, render: (a) => { const s = pick(ACCOUNT_STATUS, a.status); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
          ]}
        />
      </div>
      <AccountDrawer id={open} onClose={() => setOpen(null)} onChanged={list.reload} toast={toast} />
    </>
  );
}

function AccountDrawer({ id, onClose, onChanged, toast }: { id: string | null; onClose: () => void; onChanged: () => void; toast: ReturnType<typeof useToast> }) {
  const net = useNetwork();
  const acc = useAsync(() => (id ? net.account(id) : Promise.resolve(null)), [id]);
  const limit = useAsync(() => (id ? net.safeLimit(id).catch(() => null) : Promise.resolve(null)), [id]);
  const [newLimit, setNewLimit] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const a = acc.data;
  const status = pick(ACCOUNT_STATUS, a?.status);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      toast.error("Action failed", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Drawer open={!!id} onClose={onClose} wide title={a?.name || "Account"} subtitle={a ? accountLine(a.account_no, a.bank_code, a.home) : undefined}
      footer={a?.home && <Button icon={RefreshCcw} loading={busy === "sync"} onClick={() => run("sync", async () => { const r = await net.syncAccount(a.id); toast.success("Updated from the bank", r.daily_limit_kobo ? `Daily limit ${naira(r.daily_limit_kobo)}` : "Details updated"); acc.reload(); onChanged(); })}>Update from the bank</Button>}>
      {!a ? (
        <div className="p-5"><div className="skeleton h-4 w-2/3 rounded" /></div>
      ) : (
        <>
          <DetailList items={[
            { label: "Risk", value: <RiskScore value={a.risk} /> },
            ...(a.model ? [{ label: "Second opinion", value: <span className="inline-flex flex-wrap items-center gap-2"><RiskScore value={a.model.score} /><span className="text-xs text-[var(--muted)]">from the learning model, still in testing</span></span> }] : []),
            { label: "Status", value: <Badge tone={status.tone} icon={status.icon}>{status.label}</Badge> },
            { label: "Bank", value: a.home ? "Our customer" : bankName(a.bank_code) },
            { label: "Account opened", value: fmtDay(a.opened_at) },
            { label: "Identity checks", value: a.kyc_tier ? KYC_TIER[a.kyc_tier] ?? `Tier ${a.kyc_tier}` : "–" },
            { label: "Last 30 days", value: `${naira(a.inbound_total)} in · ${naira(a.outbound_total)} out` },
            { label: "Ring", value: a.ring_id ? <Link className="text-[var(--brand)] hover:underline" href={`/network/rings/${a.ring_id}`}>{ringName({ id: a.ring_id, number: a.ring_number })}</Link> : "Not in a ring" },
            { label: "Owner checks", value: a.customer_id ? "Owner can confirm payments with voice, iris or phone" : "Owner has not set up voice or iris" },
          ]} />
          <div className="border-t border-[var(--line)] px-5 py-4">
            <h3 className="mb-2 text-sm font-semibold text-[var(--ink)]">Why it was flagged</h3>
            {a.signals.length ? (
              <ul className="grid gap-2">
                {a.signals.map((s) => (
                  <li key={s.code} className="border-l-2 border-[var(--brand)] bg-[var(--surface-2)] px-3 py-2 text-sm">
                    <div className="font-medium">{TYPOLOGY[s.code] ?? s.code}</div>
                    <div className="text-xs text-[var(--muted)]">What we saw: {s.reason}.</div>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-[var(--muted)]">Nothing suspicious found.</p>}
          </div>
          {a.home && (
            <div className="border-t border-[var(--line)] px-5 py-4">
              <h3 className="mb-2 text-sm font-semibold text-[var(--ink)]">Customer&apos;s own daily limit</h3>
              <p className="mb-3 text-sm text-[var(--ink-2)]">
                {limit.data?.limit_kobo ? `Current daily limit ${naira(limit.data.limit_kobo)}.` : "The customer has not set a limit."}
                {limit.data?.pending_limit_kobo ? ` Raising to ${naira(limit.data.pending_limit_kobo)} on ${fmtDate(limit.data.pending_effective_at)}.` : ""}
              </p>
              <div className="flex flex-wrap items-end gap-2">
                <Field label="New daily limit (₦)" className="w-48">
                  <Input inputMode="numeric" value={newLimit} onChange={(e) => setNewLimit(e.target.value.replace(/[^\d]/g, ""))} />
                </Field>
                <Button loading={busy === "limit"} disabled={!Number(newLimit)} onClick={() => run("limit", async () => { const r = await net.setSafeLimit(a.id, Number(newLimit) * 100); toast.success("Daily limit updated", r.note ?? undefined); setNewLimit(""); limit.reload(); })}>Save</Button>
              </div>
              <p className="mt-2 text-xs text-[var(--muted)]">Lowering applies at once. Raising takes 24 hours, so nobody can raise it under pressure.</p>
            </div>
          )}
          <div className="border-t border-[var(--line)]">
            <h3 className="px-5 pt-4 text-sm font-semibold text-[var(--ink)]">Recent payments</h3>
            <ul className="divide-y divide-[var(--line)]">
              {a.recent.slice(0, 25).map((t) => (
                <li key={t.reference} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  {t.direction === "in" ? <ArrowDownLeft className="size-4 text-[var(--good)]" /> : <ArrowUpRight className="size-4 text-[var(--muted)]" />}
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{t.counterparty.name || t.counterparty.account_no}</div>
                    <div className="text-xs text-[var(--muted)]">{fmtDate(t.ts)} · {CHANNEL[t.channel] ?? t.channel}</div>
                  </div>
                  <span className="tabular-nums">{t.direction === "in" ? "+" : "−"}{naira(t.amount)}</span>
                </li>
              ))}
              {!a.recent.length && <li className="px-5 py-3 text-sm text-[var(--muted)]">No payments in the last 30 days.</li>}
            </ul>
          </div>
        </>
      )}
    </Drawer>
  );
}
