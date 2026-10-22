"use client";

/** Make a payment (a simulation): you pay a mule account from your own account. The receiver is given a mule's history,
 * the transfer goes through TheOne's real check, and a payment it stops shows up on the mule ring it was heading to. */
import { Check, CheckCircle2, ChevronDown, Loader2, type LucideIcon, Search, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Dialog, Field, Input, inputCls, PageHeader, type Tone, useToast } from "@/presentation/components/ui";
import { cx } from "@/presentation/cx";
import { naira } from "@/presentation/format";
import type { NetDecision } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";
import { NIGERIAN_BANKS, POPULAR_BANKS, type NgBank } from "./banks";

const ACCOUNT_DIGITS = 10;
// The name the demo's account check returns for any account number.
const VERIFIED_NAME = "Samuel Aluko";
const VERIFY_MS = 1000;
// Sending takes about a second, like a real transfer, even though the check itself takes milliseconds.
const SEND_MS = 1000;

// What the customer sees: a short, friendly answer. The findings stay with the fraud team (Mule rings, Payments checked).
const OUTCOME: Record<NetDecision["decision"], { title: string; tone: Tone; icon: LucideIcon; body: (amount: string, to: string) => string }> = {
  ALLOW: { title: "Payment sent", tone: "good", icon: CheckCircle2, body: (amount, to) => `${amount} has been sent to ${to}.` },
  WARN_PAYEE: {
    title: "Please check before you pay", tone: "warning", icon: ShieldAlert,
    body: (_, to) => `The account you are sending money to (${to}) looks suspicious. Please contact your bank for more details before you pay.`,
  },
  STEP_UP_OWNER: {
    title: "Please confirm it is you", tone: "warning", icon: ShieldAlert,
    body: () => "This payment is unusual for your account. Please contact your bank to confirm it before it is sent.",
  },
  HOLD: {
    title: "Payment not sent", tone: "critical", icon: ShieldAlert,
    body: (amount) => `The account you are sending money to looks suspicious, so we have stopped this payment to protect you. Your ${amount} is safe in your account. Please contact your bank for more details.`,
  },
};

const withCommas = (digits: string) => (digits ? Number(digits).toLocaleString("en-NG") : "");

function BankLogo({ bank, size = 28 }: { bank: NgBank; size?: number }) {
  const box = { width: size, height: size };
  if (bank.logo) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={`/banks/${bank.slug}.png`} alt="" className="shrink-0 rounded-[6px] object-contain" style={box} loading="lazy" />;
  }
  const initials = bank.name.replace(/[^A-Za-z ]/g, "").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  return (
    <span className="inline-flex shrink-0 items-center justify-center rounded-[6px] bg-[var(--surface-2)] text-[11px] font-semibold text-[var(--ink-2)]" style={box} aria-hidden>
      {initials}
    </span>
  );
}

function BankSelect({ value, onChange }: { value: NgBank | null; onChange: (b: NgBank) => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  const popular = useMemo(() => POPULAR_BANKS.map((c) => NIGERIAN_BANKS.find((b) => b.code === c)!).filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name)), []);
  const term = q.toLowerCase().trim();
  const groups: { title: string; banks: NgBank[] }[] = term
    ? [{ title: "", banks: NIGERIAN_BANKS.filter((b) => b.name.toLowerCase().includes(term)) }]
    : [{ title: "Popular", banks: popular }, { title: "All banks", banks: NIGERIAN_BANKS }];
  const choose = (b: NgBank) => { onChange(b); setOpen(false); setQ(""); };
  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}
        className={cx(inputCls, "flex h-11 w-full items-center gap-3 text-left")}>
        {value && <BankLogo bank={value} size={24} />}
        <span className={cx("min-w-0 flex-1 truncate", !value && "text-[var(--muted)]")}>{value ? value.name : "Choose a bank"}</span>
        <ChevronDown className="size-4 shrink-0 text-[var(--muted)]" />
      </button>
      {open && (
        <div className="absolute inset-x-0 z-20 mt-1 overflow-hidden rounded-[8px] border border-[var(--line)] bg-[var(--surface)] shadow-lg">
          <div className="flex items-center gap-2 border-b border-[var(--line)] px-3">
            <Search className="size-4 text-[var(--muted)]" />
            <input autoFocus autoComplete="off" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${NIGERIAN_BANKS.length} banks`}
              className="h-10 w-full min-w-0 bg-transparent text-sm" style={{ outline: "none" }} />
          </div>
          <div role="listbox" className="max-h-80 overflow-auto py-1">
            {groups.map((g) => (
              <div key={g.title || "results"}>
                {g.title && <p className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-[var(--muted)]">{g.title}</p>}
                {g.banks.map((b) => (
                  <button key={`${g.title}-${b.slug}`} type="button" role="option" aria-selected={value?.slug === b.slug} onClick={() => choose(b)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-[var(--surface-2)]">
                    <BankLogo bank={b} size={28} />
                    <span className="min-w-0 flex-1 break-words">{b.name}</span>
                    {value?.slug === b.slug && <Check className="size-4 text-[var(--brand)]" />}
                  </button>
                ))}
                {g.banks.length === 0 && <p className="px-3 py-3 text-sm text-[var(--muted)]">No bank matches “{q}”.</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function SimulatePaymentPage() {
  const net = useNetwork();
  const toast = useToast();
  const [bank, setBank] = useState<NgBank | null>(null);
  const [accountNo, setAccountNo] = useState("");
  const [verified, setVerified] = useState<Record<string, string>>({});
  const [amount, setAmount] = useState("");
  const [narration, setNarration] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<NetDecision | null>(null);

  // The account check: once a bank and a full account number are in, verify who holds the account.
  const key = bank && accountNo.length === ACCOUNT_DIGITS ? `${bank.code}:${accountNo}` : null;
  useEffect(() => {
    if (!key || key in verified) return;
    const t = setTimeout(() => setVerified((m) => ({ ...m, [key]: VERIFIED_NAME })), VERIFY_MS);
    return () => clearTimeout(t);
  }, [key, verified]);
  const name = key ? verified[key] : undefined;
  const ready = !!bank && !!name && Number(amount) > 0;

  /** After each payment the form starts blank again: every detail is entered by the person paying. */
  function done() {
    setResult(null);
    setBank(null);
    setAccountNo("");
    setAmount("");
    setNarration("");
  }

  async function send() {
    setBusy(true);
    try {
      const [d] = await Promise.all([
        net.simulateMulePayment(bank!.code, accountNo, name!, Number(amount) * 100),
        new Promise((done) => setTimeout(done, SEND_MS)),
      ]);
      setResult(d);
    } catch (e) {
      toast.error("Could not send the payment", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Make a payment"
        subtitle="Send money to a mule account from your own account, and watch TheOne stop it before it leaves the bank."
      />
      <div className="px-4 py-6 sm:px-6 lg:px-8">
        <section className="rounded-[8px] border border-[var(--line)] bg-[var(--surface)]" aria-label="Transfer">
          <div className="border-b border-[var(--line)] px-5 py-4 sm:px-6">
            <h2 className="text-base font-semibold">Transfer to a bank account</h2>
          </div>

          <div className="grid gap-6 px-5 py-6 sm:px-6">
            <div className="grid gap-4 md:grid-cols-3">
              <Field label="Bank">
                <BankSelect value={bank} onChange={(b) => { setBank(b); setResult(null); }} />
              </Field>
              <Field label="Account number">
                <Input className="h-11 tracking-wider tabular-nums" inputMode="numeric" autoComplete="off" name="theone-account-number" maxLength={ACCOUNT_DIGITS} placeholder="10 digits" value={accountNo}
                  onChange={(e) => { setAccountNo(e.target.value.replace(/\D/g, "").slice(0, ACCOUNT_DIGITS)); setResult(null); }} />
              </Field>
              <Field label="Account name">
                <div className={cx(inputCls, "flex h-11 items-center gap-2", name && "border-[var(--good)]")} aria-live="polite">
                  {!key && <span className="text-[var(--muted)]">{bank ? "Enter the 10-digit account number" : "Choose a bank first"}</span>}
                  {key && !name && <><Loader2 className="size-4 animate-spin text-[var(--muted)]" /><span className="text-[var(--muted)]">Verifying account…</span></>}
                  {name && <><Check className="size-4 shrink-0 text-[var(--good)]" /><span className="truncate font-semibold uppercase">{name}</span></>}
                </div>
              </Field>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <Field label="Amount">
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]">₦</span>
                  <Input className="h-11 pl-7 text-base font-semibold tabular-nums" inputMode="numeric" autoComplete="off" name="theone-amount" placeholder="0" value={withCommas(amount)}
                    onChange={(e) => { setAmount(e.target.value.replace(/\D/g, "").slice(0, 12)); setResult(null); }} />
                </div>
              </Field>
              <div className="md:col-span-2">
                <Field label="Narration (optional)">
                  <Input className="h-11" autoComplete="off" name="theone-narration" value={narration} maxLength={60} placeholder="What is it for?" onChange={(e) => setNarration(e.target.value)} />
                </Field>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] px-5 py-4 sm:px-6">
            <p className="text-sm text-[var(--muted)]">
              {name && Number(amount) > 0
                ? <>Sending <b className="text-[var(--ink)]">{naira(Number(amount) * 100)}</b> to <b className="text-[var(--ink)]">{name}</b>, {bank?.name}.</>
                : "Choose the bank, verify the account and enter the amount."}
            </p>
            <Button variant="primary" loading={busy} disabled={!ready} onClick={send}>{busy ? "Sending…" : "Send payment"}</Button>
          </div>
        </section>
      </div>

      {result && <ResultDialog d={result} onClose={done} />}
    </>
  );
}

function ResultDialog({ d, onClose }: { d: NetDecision; onClose: () => void }) {
  const o = OUTCOME[d.decision];
  return (
    <Dialog open onClose={onClose} title={o.title} icon={o.icon} tone={o.tone}
      description={o.body(naira(d.amount_kobo), d.beneficiary.name || d.beneficiary.account_no)}
      footer={<Button variant="primary" onClick={onClose}>OK</Button>} />
  );
}
