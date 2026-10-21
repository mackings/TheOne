"use client";

import { ArrowRight, Hand, Network, ShieldAlert, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Button, DataTable, EmptyState, InlineError, Kpi, KpiStrip, MixBar, PageHeader, RiskScore, Section } from "@/presentation/components/ui";

import { fmtDate, naira, ringName } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";
import { DECISION, pick, RING_STATUS, TYPOLOGY } from "@/presentation/status";
import { useNetwork } from "@/presentation/hooks/gateways";

const EVERY = 30_000;

export function OverviewPage() {
  const net = useNetwork();
  const router = useRouter();
  const summary = useAsync(() => net.summary(), [], { every: EVERY });
  const rings = useAsync(() => net.rings(), [], { every: EVERY });
  const decisions = useAsync(() => net.decisions(500), [], { every: EVERY });
  const bank = useAsync(() => net.bankActions(), [], { every: EVERY });

  const s = summary.data;
  const d = decisions.data ?? [];
  const count = (k: string) => d.filter((x) => x.decision === k).length;
  const openRings = (rings.data ?? []).filter((r) => r.status === "open");
  const holdsDone = (bank.data ?? []).filter((a) => a.status === "done" && a.kind !== "remove_hold").length;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Suspicious accounts, mule rings and payments checked today."
        actions={
          <Link href="/network">
            <Button variant="primary" icon={Network}>
              See mule rings
            </Button>
          </Link>
        }
      />
      <InlineError error={summary.error} onRetry={summary.reload} />

      <KpiStrip cols={4}>
        <Kpi label="Suspicious accounts" icon={Users} tone="serious" value={s?.flagged_accounts ?? "–"} sub={s ? `out of ${s.accounts.toLocaleString()} accounts checked` : undefined} />
        <Kpi label="Open mule rings" icon={Network} tone="critical" value={rings.data ? openRings.length : "–"} sub={rings.data ? `${rings.data.length} found in total` : undefined} />
        <Kpi label="Payments held" icon={Hand} tone="critical" value={decisions.data ? count("HOLD") : "–"} sub={decisions.data ? (d.length ? `out of ${d.length} payments checked` : "no payments checked yet") : undefined} />
        <Kpi label="Holds and blocks at the bank" icon={ShieldAlert} tone="info" value={bank.data ? holdsDone : "–"} sub={s && s.bank_connector === "none" ? "no bank connected" : undefined} />
      </KpiStrip>

      <Section title="Payments checked" description="What happened to each payment TheOne checked before the money left." actions={<Link href="/network/decisions" className="text-sm font-medium text-[var(--brand)]">See all</Link>}>
        {d.length ? (
          <MixBar
            ariaLabel="Payments checked, by outcome"
            parts={[
              { key: "ALLOW", label: "Allowed", value: count("ALLOW"), color: "var(--good)", icon: DECISION.ALLOW.icon },
              { key: "WARN_PAYEE", label: "Sender warned", value: count("WARN_PAYEE"), color: "var(--warning)", icon: DECISION.WARN_PAYEE.icon },
              { key: "STEP_UP_OWNER", label: "Owner asked to confirm", value: count("STEP_UP_OWNER"), color: "var(--serious)", icon: DECISION.STEP_UP_OWNER.icon },
              { key: "HOLD", label: "Held", value: count("HOLD"), color: "var(--critical)", icon: DECISION.HOLD.icon },
            ]}
          />
        ) : (
          <p className="text-sm text-[var(--muted)]">No payments checked yet. They appear here once the bank&apos;s payment system starts asking TheOne.</p>
        )}
      </Section>

      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3 sm:px-6 lg:px-8">
          <h2 className="text-sm font-semibold">Riskiest mule rings</h2>
          <Link href="/network" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--brand)]">
            All rings <ArrowRight className="size-3.5" />
          </Link>
        </div>
        <DataTable
          rows={(rings.data ?? []).slice(0, 8)}
          loading={rings.loading}
          rowKey={(r) => r.id}
          onRowClick={(r) => router.push(`/network/rings/${r.id}`)}
          pageSize={8}
          empty={<EmptyState icon={Network} title="No mule rings found" description="Add demo data or import transfers on the Data & bank page." />}
          columns={[
            { key: "ring", header: "Ring", render: (r) => <span className="whitespace-nowrap font-medium">{ringName(r)}</span> },
            { key: "score", header: "Risk", render: (r) => <RiskScore value={r.score} /> },
            { key: "size", header: "Accounts", align: "right", hideBelow: "sm", render: (r) => r.size },
            { key: "victims", header: "People who paid in", align: "right", hideBelow: "md", render: (r) => r.possible_victims },
            { key: "paid", header: "Money paid in", align: "right", hideBelow: "sm", render: (r) => naira(r.victim_inflow) },
            { key: "cash", header: "Taken out as cash", align: "right", hideBelow: "lg", render: (r) => naira(r.cash_out_total) },
            { key: "typ", header: "Main warning sign", hideBelow: "xl", render: (r) => TYPOLOGY[Object.keys(r.typologies)[0]] ?? "–" },
            { key: "last", header: "Last activity", hideBelow: "xl", render: (r) => <span className="whitespace-nowrap text-xs text-[var(--muted)]">{fmtDate(r.last_seen)}</span> },
            { key: "status", header: "Status", render: (r) => { const st = pick(RING_STATUS, r.status); return <Badge tone={st.tone} icon={st.icon}>{st.label}</Badge>; } },
          ]}
        />
      </div>
    </>
  );
}
