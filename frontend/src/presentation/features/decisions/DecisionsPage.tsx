"use client";

import { ArrowLeftRight, Ban, CheckCircle2, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  DetailList,
  Dialog,
  Drawer,
  EmptyState,
  Field,
  FilterBar,
  InlineError,
  Input,
  inputCls,
  PageHeader,
  RiskScore,
  SearchInput,
  Segmented,
  Select,
  useToast,
} from "@/presentation/components/ui";
import { accountLine, fmtDate, naira } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { DECISION, DECISION_STATUS, pick, TYPOLOGY } from "@/presentation/status";
import { useActor } from "@/presentation/hooks/useActor";
import type { AccountBrief, NetDecision } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

const METHOD: Record<string, string> = { voice: "voice", iris: "iris (eye scan)", device: "fingerprint on their phone", bank_otp: "the bank's one-time code" };

type Kind = "all" | "ALLOW" | "WARN_PAYEE" | "STEP_UP_OWNER" | "HOLD";

export function DecisionsPage() {
  const net = useNetwork();
  const toast = useToast();
  const list = useAsync(() => net.decisions(500), [], { every: 20_000 });
  const [kind, setKind] = useState<Kind>("all");
  const [status, setStatus] = useState("");
  const [minAmount, setMinAmount] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<NetDecision | null>(null);
  const [tester, setTester] = useState(false);

  const all = useMemo(() => list.data ?? [], [list.data]);
  const rows = all.filter(
    (d) =>
      (kind === "all" || d.decision === kind) &&
      (!status || d.status === status) &&
      (!minAmount || d.amount_kobo >= Number(minAmount) * 100) &&
      (!q || `${d.source.name} ${d.source.account_no} ${d.beneficiary.name} ${d.beneficiary.account_no}`.toLowerCase().includes(q.toLowerCase())),
  );
  const count = (k: string) => all.filter((d) => d.decision === k).length;

  return (
    <>
      <PageHeader
        title="Payments checked"
        subtitle="Every payment TheOne checked before the money left, what it decided, and why."
        actions={<Button variant="primary" icon={Plus} onClick={() => setTester(true)}>Try a payment</Button>}
      />
      <InlineError error={list.error} onRetry={list.reload} />
      {!list.loading && !all.length ? (
        <div className="border-b border-[var(--line)] bg-[var(--surface)] py-6">
          <EmptyState icon={ArrowLeftRight} title="No payments checked yet" description="The bank's payment system asks TheOne before each payment leaves. Use “Try a payment” to see how it works."
            action={<Button icon={Plus} onClick={() => setTester(true)}>Try a payment</Button>} />
        </div>
      ) : (
      <>
      <FilterBar
        right={<span className="text-xs text-[var(--muted)]">{rows.length} of {all.length}</span>}
        active={(status ? 1 : 0) + (minAmount ? 1 : 0)}
        more={
          <>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-56" aria-label="What happened next"
              options={[{ value: "", label: "Any outcome" }, ...Object.entries(DECISION_STATUS).map(([k, v]) => ({ value: k, label: v.label }))]} />
            <Input value={minAmount} onChange={(e) => setMinAmount(e.target.value.replace(/[^\d]/g, ""))} placeholder="At least ₦" className="w-40" inputMode="numeric" aria-label="Minimum amount" />
          </>
        }
      >
        <Segmented<Kind>
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: "All", count: all.length },
            { value: "HOLD", label: "Held", count: count("HOLD") },
            { value: "STEP_UP_OWNER", label: "Owner asked", count: count("STEP_UP_OWNER") },
            { value: "WARN_PAYEE", label: "Sender warned", count: count("WARN_PAYEE") },
            { value: "ALLOW", label: "Allowed", count: count("ALLOW") },
          ]}
        />
        <SearchInput value={q} onChange={setQ} placeholder="Sender or receiver" className="w-full sm:w-56" />
      </FilterBar>
      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<NetDecision>
          rows={rows}
          loading={list.loading}
          rowKey={(d) => d.id}
          onRowClick={setOpen}
          selectedKey={open?.id}
          initialSort={{ key: "when", dir: "desc" }}
          empty={<EmptyState icon={ArrowLeftRight} title="No payments match" description="Choose “All” or clear a filter to see more." />}
          columns={[
            { key: "when", header: "Time", sort: (d) => d.created_at, render: (d) => <span className="whitespace-nowrap text-xs">{fmtDate(d.created_at)}</span> },
            { key: "from", header: "From", sort: (d) => d.source.name, render: (d) => <Party p={d.source} /> },
            { key: "to", header: "To", hideBelow: "sm", sort: (d) => d.beneficiary.name, render: (d) => <Party p={d.beneficiary} /> },
            { key: "amount", header: "Amount", align: "right", sort: (d) => d.amount_kobo, render: (d) => <span className="font-medium">{naira(d.amount_kobo)}</span> },
            { key: "decision", header: "TheOne decided", sort: (d) => d.decision, render: (d) => { const s = pick(DECISION, d.decision); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
            { key: "status", header: "What happened", hideBelow: "md", sort: (d) => d.status, render: (d) => { const s = pick(DECISION_STATUS, d.status); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
            { key: "risk", header: "Risk", hideBelow: "lg", sort: (d) => Math.max(d.source_risk, d.sender_risk ?? 0, d.beneficiary_risk), render: (d) => <RiskScore value={Math.max(d.source_risk, d.sender_risk ?? 0, d.beneficiary_risk)} /> },
          ]}
        />
      </div>
      </>
      )}
      <DecisionDrawer d={open} onClose={() => setOpen(null)} onChanged={() => { list.reload(); setOpen(null); }} toast={toast} />
      <TesterDialog open={tester} onClose={() => setTester(false)} onDone={list.reload} />
    </>
  );
}

function Party({ p }: { p: { name: string; bank_code: string; account_no: string } }) {
  return (
    <div className="min-w-0">
      <div className="truncate font-medium">{p.name || "Unknown"}</div>
      <div className="text-xs text-[var(--muted)]">{accountLine(p.account_no, p.bank_code)}</div>
    </div>
  );
}

function DecisionDrawer({ d, onClose, onChanged, toast }: { d: NetDecision | null; onClose: () => void; onChanged: () => void; toast: ReturnType<typeof useToast> }) {
  const net = useNetwork();
  const [actor, setActor] = useActor();
  const [review, setReview] = useState<"release" | "block" | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  if (!d) return null;
  const dec = pick(DECISION, d.decision);
  const st = pick(DECISION_STATUS, d.status);
  const reviewable = d.status === "pending_review" || d.status === "duress_hold" || d.status === "pending";
  return (
    <>
      <Drawer open onClose={onClose} wide title={`${naira(d.amount_kobo)} · ${d.source.name || d.source.account_no}`} subtitle={fmtDate(d.created_at)}
        footer={reviewable && (
          <>
            <Button icon={Ban} onClick={() => setReview("block")}>Stop the payment</Button>
            <Button variant="primary" icon={CheckCircle2} onClick={() => setReview("release")}>Let it go through</Button>
          </>
        )}>
        <DetailList items={[
          { label: "TheOne decided", value: <Badge tone={dec.tone} icon={dec.icon}>{dec.label}</Badge> },
          { label: "What happened", value: <Badge tone={st.tone} icon={st.icon}>{st.label}</Badge> },
          { label: "From", value: <Party p={d.source} /> },
          { label: "To", value: <Party p={d.beneficiary} /> },
          { label: "Is this payment unusual?", value: <RiskScore value={d.sender_risk ?? 0} /> },
          { label: "Is the sender a mule?", value: <RiskScore value={d.source_risk} /> },
          { label: "Is the receiver a mule?", value: <RiskScore value={d.beneficiary_risk} /> },
          ...(d.step_up_methods.length ? [{ label: "Owner can confirm with", value: d.step_up_methods.map((m) => METHOD[m] ?? m).join(", ") }] : []),
          ...(d.resolution_note ? [{ label: "Note", value: d.resolution_note }] : []),
          { label: "Time taken", value: d.latency_ms < 1000 ? "Less than a second" : `${(d.latency_ms / 1000).toFixed(1)} seconds` },
        ]} />
        <div className="border-t border-[var(--line)] px-5 py-4">
          <h3 className="mb-2 text-sm font-semibold text-[var(--ink)]">Why</h3>
          <ul className="grid gap-1.5 text-sm">
            {d.reasons.map((r) => <li key={r} className="border-l-2 border-[var(--line-strong)] pl-3">{r}</li>)}
          </ul>
        </div>
        {d.status === "duress_hold" && (
          <div className="border-t border-[var(--line)] bg-[var(--critical-soft)] px-5 py-4 text-sm">
            The customer secretly signalled that someone is forcing them to pay. Their app showed the payment as sent so they stay safe. Reach them on a number or channel you know is safe before letting it go.
          </div>
        )}
      </Drawer>
      <ConfirmDialog
        open={!!review}
        onCancel={() => setReview(null)}
        busy={busy}
        danger={review === "block"}
        title={review === "release" ? "Let this payment go through?" : "Stop this payment?"}
        message={review === "release" ? "The money is sent to the receiver. Make sure the customer confirmed it on a phone number or channel you trust." : "The money will not be sent. Tell the customer through the bank's usual channel."}
        confirmLabel={review === "release" ? "Let it go through" : "Stop the payment"}
        onConfirm={async () => {
          setBusy(true);
          try {
            await net.reviewDecision(d.id, review!, actor || "analyst", note || undefined);
            toast.success(review === "release" ? "Payment sent on" : "Payment stopped");
            setReview(null);
            onChanged();
          } catch (e) {
            toast.error("Could not save", (e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="grid gap-3">
          <Field label="Your name (kept in the record)"><Input value={actor} onChange={(e) => setActor(e.target.value)} /></Field>
          <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. customer confirmed by phone" /></Field>
        </div>
      </ConfirmDialog>
    </>
  );
}

function AccountPicker({ label, value, onChange }: { label: string; value: AccountBrief | null; onChange: (a: AccountBrief | null) => void }) {
  const net = useNetwork();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<AccountBrief[]>([]);
  const searching = q.trim().length >= 2;
  useEffect(() => {
    if (!searching) return;
    const t = setTimeout(() => net.search(q).then(setHits).catch(() => setHits([])), 200);
    return () => clearTimeout(t);
  }, [net, q, searching]);
  return (
    <Field label={label}>
      {value ? (
        <div className={`${inputCls} flex w-full items-center justify-between`}>
          <span className="truncate">{value.name} <span className="text-[var(--muted)]">· {accountLine(value.account_no, value.bank_code, value.home)}</span></span>
          <button className="text-xs font-medium text-[var(--brand)]" onClick={() => onChange(null)}>Change</button>
        </div>
      ) : (
        <div className="relative">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or account number" />
          {searching && hits.length > 0 && (
            <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-[6px] border border-[var(--line)] bg-[var(--surface)] shadow-lg">
              {hits.map((h) => (
                <li key={h.id}>
                  <button className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--surface-2)]" onClick={() => { onChange(h); setQ(""); setHits([]); }}>
                    <span className="truncate">{h.name} <span className="text-[var(--muted)]">· {accountLine(h.account_no, h.bank_code, h.home)}</span></span>
                    <RiskScore value={h.risk} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Field>
  );
}

function TesterDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const net = useNetwork();
  const toast = useToast();
  const [src, setSrc] = useState<AccountBrief | null>(null);
  const [dst, setDst] = useState<AccountBrief | null>(null);
  const [amount, setAmount] = useState("50000");
  const [result, setResult] = useState<NetDecision | null>(null);
  const [busy, setBusy] = useState(false);
  const dec = result ? pick(DECISION, result.decision) : null;
  return (
    <Dialog open={open} onClose={() => { setResult(null); onClose(); }} title="Try a payment"
      description="See what TheOne would decide before money leaves. Try a suspicious account as the sender, then as the receiver, then two ordinary customers."
      footer={<><Button onClick={onClose}>Close</Button><Button variant="primary" loading={busy} disabled={!src || !dst || !Number(amount)} onClick={async () => {
        setBusy(true);
        try { setResult(await net.decide(src!, dst!, Number(amount) * 100)); onDone(); } catch (e) { toast.error("Could not check the payment", (e as Error).message); } finally { setBusy(false); }
      }}>Check payment</Button></>}>
      <div className="grid gap-3">
        <AccountPicker label="From" value={src} onChange={setSrc} />
        <AccountPicker label="To" value={dst} onChange={setDst} />
        <Field label="Amount (₦)"><Input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ""))} /></Field>
        {result && dec && (
          <div className="border border-[var(--line)] bg-[var(--surface-2)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={dec.tone} icon={dec.icon}>{dec.label}</Badge>
              <span className="text-xs text-[var(--muted)]">decided in {result.latency_ms < 1000 ? "less than a second" : `${(result.latency_ms / 1000).toFixed(1)} seconds`}</span>
            </div>
            <ul className="mt-2 grid gap-1 text-sm">{result.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
            {result.sender_signals.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">{result.sender_signals.map((s) => <Badge key={s.code} tone="serious">{TYPOLOGY[s.code] ?? s.code}</Badge>)}</div>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
