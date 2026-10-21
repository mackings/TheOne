"use client";

/** The outbox of holds and blocks sent to the bank, with retry. */

import { Landmark, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, DataTable, EmptyState, FilterBar, InlineError, SearchInput, Segmented, Select, useToast } from "@/presentation/components/ui";
import { fmtDate } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { BANK_STATUS, pick } from "@/presentation/status";
import type { BankAction } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

const KIND_LABEL: Record<string, string> = { place_hold: "24-hour hold", remove_hold: "Lift a hold", block_pnd: "Block money going out" };

export function BankTab() {
  const net = useNetwork();
  const toast = useToast();
  const list = useAsync(() => net.bankActions(), [], { every: 20_000 });
  const [status, setStatus] = useState("all");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const all = useMemo(() => list.data ?? [], [list.data]);
  const needle = q.trim().toLowerCase();
  const rows = all.filter(
    (a) => (status === "all" || a.status === status) && (!kind || a.kind === kind) && (!needle || `${String(a.request.account_no ?? "")} ${a.reference}`.toLowerCase().includes(needle)),
  );
  const count = (st: string) => all.filter((a) => a.status === st).length;

  async function retry(a: BankAction) {
    setBusy(a.id);
    try {
      const r = await net.retryBankAction(a.id);
      if (r.status === "done") toast.success("Done at the bank", `${KIND_LABEL[r.kind] ?? r.kind} accepted.`);
      else toast.error("The bank still did not accept it", r.last_error ?? undefined);
      list.reload();
    } catch (e) {
      toast.error("Could not try again", (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <InlineError error={list.error} onRetry={list.reload} />
      <FilterBar>
        <Segmented
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "All", count: all.length },
            { value: "done", label: "Done", count: count("done") },
            { value: "failed", label: "Not done", count: count("failed") },
            { value: "recorded", label: "To do by hand", count: count("recorded") },
            { value: "shadow", label: "Test mode", count: count("shadow") },
          ]}
        />
        <div className="w-44">
          <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Action" options={[{ value: "", label: "Any action" }, ...Object.entries(KIND_LABEL).map(([k, v]) => ({ value: k, label: v }))]} />
        </div>
        <SearchInput value={q} onChange={setQ} placeholder="Account or reference" className="w-full sm:w-56" />
      </FilterBar>
      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<BankAction>
          rows={rows}
          loading={list.loading}
          rowKey={(a) => a.id}
          initialSort={{ key: "when", dir: "desc" }}
          empty={<EmptyState icon={Landmark} title="Nothing sent to the bank yet" description="Watching or confirming a ring asks the bank to hold or block those accounts. Each request shows here." />}
          columns={[
            { key: "when", header: "Time", sort: (a) => a.created_at, render: (a) => <span className="whitespace-nowrap text-xs">{fmtDate(a.created_at)}</span> },
            { key: "kind", header: "Action", sort: (a) => a.kind, render: (a) => <span className="font-medium">{KIND_LABEL[a.kind] ?? a.kind}</span> },
            { key: "acct", header: "Account", render: (a) => <span className="font-mono text-xs">{String(a.request.bank_code ?? "")} / {String(a.request.account_no ?? "")}</span> },
            { key: "status", header: "Status", sort: (a) => a.status, render: (a) => { const s = pick(BANK_STATUS, a.status); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
            { key: "detail", header: "Detail", hideBelow: "md", render: (a) => <span className="text-xs text-[var(--muted)]">{a.last_error ?? a.reference}</span> },
            { key: "tries", header: "Tries", align: "right", hideBelow: "lg", sort: (a) => a.attempts, render: (a) => a.attempts },
            {
              key: "retry",
              header: "",
              align: "right",
              render: (a) => (a.status === "failed" ? <Button size="sm" icon={RotateCcw} loading={busy === a.id} onClick={() => retry(a)}>Try again</Button> : null),
            },
          ]}
        />
      </div>
    </>
  );
}
