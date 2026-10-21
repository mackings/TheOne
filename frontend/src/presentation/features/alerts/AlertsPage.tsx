"use client";

import { CheckCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  DetailList,
  Drawer,
  EmptyState,
  Field,
  FilterBar,
  InlineError,
  Input,
  PageHeader,
  SearchInput,
  Segmented,
  Select,
  useToast,
} from "@/presentation/components/ui";
import { fmtDate, timeAgo } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { ALERT_KIND, pick, SEVERITY } from "@/presentation/status";
import { useActor } from "@/presentation/hooks/useActor";
import type { NetAlert } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

type View = "open" | "acknowledged" | "all";

export function AlertsPage() {
  const net = useNetwork();
  const toast = useToast();
  const [actor, setActor] = useActor();
  const list = useAsync(() => net.allAlerts(), [], { every: 20_000 });
  const [view, setView] = useState<View>("open");
  const [severity, setSeverity] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<NetAlert | null>(null);
  const [ack, setAck] = useState<NetAlert | null>(null);
  const [busy, setBusy] = useState(false);

  const all = useMemo(() => list.data ?? [], [list.data]);
  const isOpen = (a: NetAlert) => !a.acknowledged_by;
  const rows = all.filter(
    (a) =>
      (view === "all" || (view === "open" ? isOpen(a) : !isOpen(a))) &&
      (!severity || a.severity === severity) &&
      (!kind || a.kind === kind) &&
      (!q || a.message.toLowerCase().includes(q.toLowerCase())),
  );
  const openAll = all.filter(isOpen);

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Things that need someone on the fraud team to act."
      />
      <InlineError error={list.error} onRetry={list.reload} />
      {!list.loading && !all.length ? (
        <div className="border-b border-[var(--line)] bg-[var(--surface)] py-6">
          <EmptyState icon={CheckCheck} title="No alerts" description="When a customer signals danger or a payment goes above their own limit, it appears here straight away." />
        </div>
      ) : (
      <>
      <FilterBar
        right={<span className="text-xs text-[var(--muted)]">{rows.length} alerts</span>}
        active={(severity ? 1 : 0) + (kind ? 1 : 0)}
        more={
          <>
            <Select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-44" aria-label="How urgent"
              options={[{ value: "", label: "Any urgency" }, ...Object.entries(SEVERITY).map(([k, v]) => ({ value: k, label: v.label }))]} />
            <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-64" aria-label="Kind of alert"
              options={[{ value: "", label: "Any kind" }, ...Object.entries(ALERT_KIND).map(([k, v]) => ({ value: k, label: v }))]} />
          </>
        }
      >
        <Segmented<View> value={view} onChange={setView} options={[
          { value: "open", label: "Open", count: openAll.length },
          { value: "acknowledged", label: "Handled", count: all.length - openAll.length },
          { value: "all", label: "All", count: all.length },
        ]} />
        <SearchInput value={q} onChange={setQ} placeholder="Search alerts" className="w-full sm:w-56" />
      </FilterBar>
      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<NetAlert>
          rows={rows}
          loading={list.loading}
          rowKey={(a) => a.id}
          onRowClick={setOpen}
          selectedKey={open?.id}
          initialSort={{ key: "when", dir: "desc" }}
          empty={<EmptyState icon={CheckCheck} title={view === "open" ? "Nothing waiting" : "No alerts here"} description="New alerts appear here by themselves." />}
          columns={[
            { key: "sev", header: "How urgent", sort: (a) => ["low", "medium", "high", "critical"].indexOf(a.severity), render: (a) => { const s = pick(SEVERITY, a.severity); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
            { key: "kind", header: "What happened", sort: (a) => a.kind, render: (a) => <span className="font-medium">{ALERT_KIND[a.kind] ?? a.kind}</span> },
            { key: "msg", header: "Details", hideBelow: "md", render: (a) => <span className="line-clamp-2 text-xs text-[var(--ink-2)]">{a.message}</span> },
            { key: "when", header: "When", sort: (a) => a.created_at, render: (a) => <span className="whitespace-nowrap text-xs">{timeAgo(a.created_at)}</span> },
            { key: "state", header: "Status", render: (a) => (a.acknowledged_by ? <Badge tone="good">Handled by {a.acknowledged_by}</Badge> : <Badge tone="warning">Waiting</Badge>) },
            { key: "act", header: "", align: "right", render: (a) => (!a.acknowledged_by ? <Button size="sm" onClick={(e) => { e.stopPropagation(); setAck(a); }}>Mark as handled</Button> : null) },
          ]}
        />
      </div>
      </>
      )}
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open ? ALERT_KIND[open.kind] ?? open.kind : ""} subtitle={open ? fmtDate(open.created_at) : undefined}
        footer={open && !open.acknowledged_by && <Button variant="primary" icon={CheckCheck} onClick={() => setAck(open)}>Mark as handled</Button>}>
        {open && (
          <>
            <p className="border-b border-[var(--line)] px-5 py-4 text-sm leading-relaxed">{open.message}</p>
            <DetailList items={[
              { label: "How urgent", value: (() => { const s = pick(SEVERITY, open.severity); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; })() },
              { label: "Payment", value: open.decision_id ? <Link className="text-[var(--brand)] hover:underline" href="/network/decisions">See the payment</Link> : "–" },
              { label: "Customer", value: open.customer_id ? <Link className="text-[var(--brand)] hover:underline" href="/customers">See customers</Link> : "–" },
              { label: "Handled", value: open.acknowledged_by ? `by ${open.acknowledged_by}` : "Not yet" },
            ]} />
          </>
        )}
      </Drawer>
      <ConfirmDialog open={!!ack} onCancel={() => setAck(null)} busy={busy} title="Mark this alert as handled?"
        message={ack?.kind === "duress" ? "Only do this once someone has reached the customer on a number or channel you know is safe." : "This records that you have dealt with it, and it leaves the waiting list."}
        confirmLabel="Mark as handled"
        onConfirm={async () => {
          if (!ack) return;
          setBusy(true);
          try { await net.ackAlert(ack.id, actor || "analyst"); toast.success("Marked as handled"); setAck(null); setOpen(null); list.reload(); }
          catch (e) { toast.error("Could not save", (e as Error).message); }
          finally { setBusy(false); }
        }}>
        <Field label="Your name (kept in the record)"><Input value={actor} onChange={(e) => setActor(e.target.value)} /></Field>
      </ConfirmDialog>
    </>
  );
}
