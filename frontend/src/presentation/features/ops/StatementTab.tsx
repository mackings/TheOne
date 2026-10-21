"use client";

import { AlertTriangle, CheckCircle2, FileSearch, Info, KeyRound, Network, ShieldCheck, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  Dialog,
  Field,
  Input,
  Kpi,
  KpiStrip,
  Section,
  type Tone,
  useToast,
} from "@/presentation/components/ui";
import { fmtDay, naira } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";
import type { StatementPayment, StatementReport } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

const BAND: Record<string, { tone: Tone; verdict: string }> = {
  Low: { tone: "good", verdict: "No sign of mule activity" },
  Watch: { tone: "warning", verdict: "Some unusual activity, worth a look" },
  Elevated: { tone: "serious", verdict: "Looks like a possible mule account" },
  High: { tone: "critical", verdict: "Strong signs of a mule account" },
};

const OUTCOME: Record<string, Tone> = { Hold: "critical", "Confirm it is you": "serious", "Allowed, noted": "neutral" };

/** Paste or upload one statement; TheOne checks it for mule behaviour and replays the payment checks. */
export function StatementTab() {
  const net = useNetwork();
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<StatementReport | null>(null);
  const [fileName, setFileName] = useState("");
  const [locked, setLocked] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const file = useRef<HTMLInputElement>(null);

  function done(r: StatementReport) {
    setReport(r);
    toast[r.mule.flagged ? "warning" : "success"]("Statement checked", BAND[r.mule.band]?.verdict);
  }

  async function run() {
    setBusy(true);
    try {
      done(await net.checkStatement(text));
    } catch (e) {
      toast.error("Could not check this statement", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(f: File, pw?: string) {
    setBusy(true);
    setFileName(f.name);
    try {
      const r = await net.checkStatementFile(f, pw);
      setText(r.text);
      setLocked(null);
      setPassword("");
      done(r);
    } catch (e) {
      const msg = (e as Error).message;
      if (/password/i.test(msg)) {
        setLocked(f);
        if (pw) toast.error("Wrong password", "Check the statement password and try again.");
      } else toast.error("Could not read this file", msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Section
        title="Check a statement"
        description="Upload a PDF, CSV or text statement, or paste its text. It is checked on your server and not stored."
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the statement here, from Account Details down to the last transaction"
          className="h-40 w-full resize-y rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] p-3 font-mono text-xs outline-none focus:border-[var(--brand)]"
          aria-label="Statement text"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button variant="primary" icon={FileSearch} loading={busy} disabled={text.trim().length < 50} onClick={run}>
            Check statement
          </Button>
          <Button icon={UploadCloud} loading={busy && !!fileName} onClick={() => file.current?.click()}>
            Upload statement
          </Button>
          {text && (
            <Button variant="ghost" onClick={() => { setText(""); setReport(null); setFileName(""); }}>
              Clear
            </Button>
          )}
          <input
            ref={file}
            type="file"
            accept=".pdf,.csv,.txt,application/pdf,text/csv,text/plain"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
              e.target.value = "";
            }}
          />
          <span className="text-xs text-[var(--muted)]">{fileName ? `From ${fileName}` : "PDF, CSV or text. Password-protected PDFs are supported."}</span>
        </div>
      </Section>
      {report && <Report r={report} />}
      {report && <AddToMap report={report} text={text} />}
      <Dialog
        open={!!locked}
        onClose={() => { setLocked(null); setPassword(""); }}
        title="This statement is password protected"
        description="Banks often lock statement PDFs. Enter the password that came with it. It is used once to open the file and not kept."
        icon={KeyRound}
        tone="info"
        footer={
          <>
            <Button onClick={() => { setLocked(null); setPassword(""); }}>Cancel</Button>
            <Button variant="primary" loading={busy} disabled={!password} onClick={() => locked && upload(locked, password)}>Open statement</Button>
          </>
        }
      >
        <Field label="Statement password">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} data-autofocus onKeyDown={(e) => e.key === "Enter" && password && locked && upload(locked, password)} />
        </Field>
      </Dialog>
    </>
  );
}

/** Put the statement's transfers on the money map so it can join rings with other accounts. */
function AddToMap({ report, text }: { report: StatementReport; text: string }) {
  const net = useNetwork();
  const toast = useToast();
  const summary = useAsync(() => net.summary());
  const [bank, setBank] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof net.importStatement>> | null>(null);
  const code = bank ?? summary.data?.home_bank.code ?? "";
  const canAdd = !!report.account.account_no && !!text;

  async function add() {
    setBusy(true);
    try {
      const r = await net.importStatement(text, code.trim());
      setResult(r);
      setConfirm(false);
      toast.success("Added to the money map", `${r.transfers_added} transfers added${r.transfers_skipped ? `, ${r.transfers_skipped} already there` : ""}.`);
    } catch (e) {
      toast.error("Could not add this statement", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Add to the money map"
      description="Put this statement's transfers on the map with everything else TheOne sees, so the account can be linked into rings. Only the last 30 days count towards live scores."
    >
      {!canAdd ? (
        <p className="text-sm text-[var(--muted)]">This statement does not show its account number, so it cannot be placed on the map.</p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Bank that issued the statement (bank code)" className="w-64">
            <Input value={code} onChange={(e) => setBank(e.target.value.replace(/[^\w-]/g, ""))} />
          </Field>
          <Button icon={Network} disabled={!code.trim()} onClick={() => setConfirm(true)}>Add to money map</Button>
          {result && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone="good" icon={CheckCircle2}>{result.transfers_added} transfers added</Badge>
              <span className="text-[var(--muted)]">{result.counterparties} people and businesses, {result.with_account_number} with an account number.</span>
              {result.risk_now != null && <Badge tone={result.risk_now >= 0.6 ? "critical" : "neutral"}>Risk now {result.risk_now.toFixed(2)}</Badge>}
              {result.ring && <Link className="font-medium text-[var(--brand)] hover:underline" href={`/network/rings/${result.ring}`}>Open its ring</Link>}
            </div>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirm}
        onCancel={() => setConfirm(false)}
        onConfirm={add}
        busy={busy}
        title="Add this statement to the money map?"
        message={`${report.coverage.lines} lines from ${report.account.holder || "this account"} (${report.account.account_no}) are added as transfers. People named in the narrations are added too, by account number where the narration shows one, otherwise by name. Adding the same statement again changes nothing.`}
        confirmLabel="Add to money map"
      />
    </Section>
  );
}

function Report({ r }: { r: StatementReport }) {
  const band = BAND[r.mule.band] ?? BAND.Low;
  const questioned = r.payments.filter((p) => p.outcome !== "Allowed, noted");
  const selfShare = r.totals.out ? Math.round((100 * r.totals.self_out) / r.totals.out) : 0;
  return (
    <>
      <Section>
        <div className="flex flex-wrap items-start gap-4">
          <div className="rounded-full p-2.5" style={{ background: `var(--${band.tone}-soft)` }}>
            {r.mule.flagged ? (
              <AlertTriangle className="size-6" style={{ color: `var(--${band.tone})` }} />
            ) : (
              <ShieldCheck className="size-6" style={{ color: `var(--${band.tone})` }} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{band.verdict}</h2>
              <Badge tone={band.tone}>
                {r.mule.band} · {r.mule.score.toFixed(2)}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {r.account.holder || "Account"} · {r.account.account_no || "no account number"} · {fmtDay(r.coverage.first)} – {fmtDay(r.coverage.last)} ·{" "}
              {r.coverage.lines} lines read{r.coverage.account_numbers_found ? `, ${r.coverage.account_numbers_found} with an account number` : ""}
            </p>
            {r.coverage.truncated && (
              <p className="mt-2 flex items-start gap-1.5 text-xs text-[var(--warn)]">
                <Info className="mt-0.5 size-3.5 shrink-0" />
                The statement text was cut off, so only transactions up to {fmtDay(r.coverage.last)} were checked.
              </p>
            )}
          </div>
        </div>
      </Section>

      <KpiStrip cols={4}>
        <Kpi label="Money in" value={naira(r.totals.in)} sub={`${r.totals.credits} credits`} />
        <Kpi label="Money out" value={naira(r.totals.out)} sub={`${r.totals.debits} payments · ${naira(r.totals.fees)} charges`} />
        <Kpi label="Balance range" value={r.totals.min_balance != null ? naira(r.totals.min_balance) : "–"} sub={r.totals.max_balance != null ? `up to ${naira(r.totals.max_balance)}` : "no running balance shown"} />
        <Kpi label="To own accounts" value={`${selfShare}%`} sub="of money going out" />
      </KpiStrip>

      <div className="grid border-b border-[var(--line)] bg-[var(--surface)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:divide-x lg:divide-[var(--line)]">
        <div className="px-4 py-5 sm:px-6 lg:px-8">
          <h2 className="mb-3 text-sm font-semibold">In plain words</h2>
          <ul className="grid gap-2 text-sm text-[var(--ink-2)]">
            {r.summary.map((s) => (
              <li key={s} className="flex gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-[var(--brand)]" />
                {s}
              </li>
            ))}
          </ul>
          <h3 className="mb-2 mt-5 text-sm font-semibold text-[var(--ink)]">Signs of everyday use</h3>
          <div className="flex flex-wrap gap-2">
            <Badge>{r.everyday.bills_and_data} bills, data and airtime</Badge>
            <Badge>{r.everyday.businesses_paid} businesses paid</Badge>
            <Badge>{r.everyday.people_paid} people paid</Badge>
            {r.everyday.card_funding > 0 && <Badge>{r.everyday.card_funding} card top-ups</Badge>}
          </div>
        </div>
        <div className="border-t border-[var(--line)] lg:border-t-0">
          <h2 className="border-b border-[var(--line)] px-4 py-4 text-sm font-semibold sm:px-6">Mule checks</h2>
          <ul className="divide-y divide-[var(--line)]">
            {r.mule.checks.map((c) => (
              <li key={c.code} className="flex items-start gap-3 px-4 py-3 sm:px-6">
                {c.fired ? (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[var(--critical)]" />
                ) : (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--good)]" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{c.title}</div>
                  <div className="text-xs text-[var(--muted)]">{c.detail}</div>
                </div>
                <Badge tone={c.fired ? "critical" : "good"}>{c.fired ? "Seen" : "Not seen"}</Badge>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Section
        title="Payments TheOne would have questioned"
        flush
        description="Each payment is checked against the history before it, as if TheOne had been running when it was made."
      >
        <DataTable<StatementPayment>
          rows={r.payments}
          rowKey={(p) => `${p.date}-${p.to}-${p.amount}`}
          initialSort={{ key: "date", dir: "asc" }}
          pageSize={10}
          empty={<p className="px-4 py-6 text-sm text-[var(--muted)] sm:px-6 lg:px-8">No payment stood out against this account&apos;s own history.</p>}
          columns={[
            { key: "date", header: "Date", sort: (p) => p.date, render: (p) => <span className="whitespace-nowrap text-xs">{fmtDay(p.date)}</span> },
            { key: "to", header: "To", render: (p) => <span className="font-medium">{p.to}</span> },
            { key: "amount", header: "Amount", align: "right", sort: (p) => p.amount, render: (p) => naira(p.amount) },
            { key: "outcome", header: "TheOne would", render: (p) => <Badge tone={OUTCOME[p.outcome] ?? "neutral"}>{p.outcome}</Badge> },
            { key: "why", header: "Why", hideBelow: "md", render: (p) => <span className="text-xs text-[var(--ink-2)]">{p.reasons.join("; ")}</span> },
          ]}
        />
        {questioned.length > 0 && (
          <p className="border-t border-[var(--line)] px-4 py-3 text-xs text-[var(--muted)] sm:px-6 lg:px-8">
            &quot;Confirm it is you&quot; means the owner would approve with their voice, eye or bank OTP before the money left.
          </p>
        )}
      </Section>

      <div className="grid border-b border-[var(--line)] bg-[var(--surface)] lg:grid-cols-2 lg:divide-x lg:divide-[var(--line)]">
        <PartyList title="Paid the most" rows={r.top_payees.map((p) => ({ name: p.name, sub: `${p.count} payment${p.count > 1 ? "s" : ""}${p.bank ? ` · ${p.bank}` : ""}`, total: p.total }))} />
        <PartyList title="Money came from" rows={r.payers.map((p) => ({ name: p.name, sub: `${p.count} credit${p.count > 1 ? "s" : ""}${p.self ? " · own account" : ""}`, total: p.total }))} />
      </div>

      <Section>
        <ul className="grid gap-1.5 text-xs text-[var(--muted)]">
          {r.limits.map((l) => (
            <li key={l} className="flex items-start gap-1.5">
              <Info className="mt-0.5 size-3.5 shrink-0" />
              {l}
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}

function PartyList({ title, rows }: { title: string; rows: { name: string; sub: string; total: number }[] }) {
  return (
    <div className="border-t border-[var(--line)] first:border-t-0 lg:border-t-0">
      <h2 className="border-b border-[var(--line)] px-4 py-4 text-sm font-semibold sm:px-6 lg:px-8">{title}</h2>
      <ul className="divide-y divide-[var(--line)]">
        {rows.map((p) => (
          <li key={p.name} className="flex items-center gap-3 px-4 py-2.5 text-sm sm:px-6 lg:px-8">
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{p.name}</div>
              <div className="text-xs text-[var(--muted)]">{p.sub}</div>
            </div>
            <span className="tabular-nums">{naira(p.total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
