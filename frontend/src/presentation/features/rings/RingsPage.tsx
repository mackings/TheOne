"use client";

import { Database, Download, FlaskConical, Network, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  FilterBar,
  InlineError,
  Kpi,
  KpiStrip,
  PageHeader,
  RiskScore,
  SearchInput,
  Segmented,
  Select,
  useToast,
} from "@/presentation/components/ui";
import { fmtDay, naira, ringName } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { pick, RING_STATUS, TYPOLOGY } from "@/presentation/status";
import type { RingListItem } from "@/domain/network";
import { useDocuments, useNetwork } from "@/presentation/hooks/gateways";

type StatusFilter = "all" | "open" | "confirmed" | "dismissed";

export function RingsPage() {
  const documents = useDocuments();
  const net = useNetwork();
  const router = useRouter();
  const toast = useToast();
  const summary = useAsync(() => net.summary());
  const rings = useAsync(() => net.rings(), [], { every: 30_000 });
  const [status, setStatus] = useState<StatusFilter>("all");
  const [risk, setRisk] = useState("0");
  const [typology, setTypology] = useState("");
  const [q, setQ] = useState("");
  const [confirmSim, setConfirmSim] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const all = useMemo(() => rings.data ?? [], [rings.data]);
  const typologies = useMemo(() => Array.from(new Set(all.flatMap((r) => Object.keys(r.typologies)))).sort(), [all]);
  const rows = useMemo(
    () =>
      all.filter((r) => {
        if (status !== "all" && r.status !== status) return false;
        if (r.score < Number(risk)) return false;
        if (typology && !(typology in r.typologies)) return false;
        if (q) {
          const t = q.toLowerCase();
          const hay = [r.id, String(r.number ?? ""), ...r.top_connected.flatMap((a) => [a.name, a.account_no])].join(" ").toLowerCase();
          if (!hay.includes(t)) return false;
        }
        return true;
      }),
    [all, status, risk, typology, q],
  );
  const counts = (st: string) => all.filter((r) => r.status === st).length;
  const reloadAll = () => [summary, rings].forEach((x) => x.reload());

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
    <>
      <PageHeader
        title="Mule rings"
        subtitle="Groups of accounts that collect money from many people and quickly move it on."
        actions={
          <>
            <Button icon={RefreshCw} loading={busy === "analyse"} onClick={() => run("analyse", async () => { await net.analyse(); reloadAll(); toast.success("Checked again", "Every account was scored again with the latest data."); })}>
              Check again
            </Button>
            <Button icon={Download} disabled={!all.length} onClick={() => run("csv", () => documents.open("/network/report.csv", "theone-mule-rings.csv"))}>
              Export
            </Button>
            {summary.data?.simulation_enabled && (
              <Button variant="ghost" icon={FlaskConical} onClick={() => setConfirmSim(true)}>
                Demo data
              </Button>
            )}
          </>
        }
      />
      <InlineError error={rings.error} onRetry={rings.reload} />

      <KpiStrip cols={4}>
        <Kpi label="Rings found" value={rings.data ? all.length : "–"} sub={`${counts("open")} open · ${counts("confirmed")} confirmed`} />
        <Kpi label="Accounts in rings" value={rings.data ? all.reduce((a, r) => a + r.size, 0) : "–"} />
        <Kpi label="Paid in by possible victims" value={rings.data ? naira(all.reduce((a, r) => a + r.victim_inflow, 0)) : "–"} />
        <Kpi label="Taken out as cash" value={rings.data ? naira(all.reduce((a, r) => a + r.cash_out_total, 0)) : "–"} />
      </KpiStrip>

      <FilterBar
        right={<span className="text-xs text-[var(--muted)]">{rows.length} of {all.length} rings</span>}
        active={(risk !== "0" ? 1 : 0) + (typology ? 1 : 0)}
        more={
          <>
            <Select
              value={risk}
              onChange={(e) => setRisk(e.target.value)}
              className="w-48"
              aria-label="Risk"
              options={[
                { value: "0", label: "Any risk" },
                { value: "0.6", label: "High and very high" },
                { value: "0.85", label: "Very high only" },
              ]}
            />
            <Select
              value={typology}
              onChange={(e) => setTypology(e.target.value)}
              className="w-64"
              aria-label="Warning sign"
              options={[{ value: "", label: "Any warning sign" }, ...typologies.map((t) => ({ value: t, label: TYPOLOGY[t] ?? t }))]}
            />
          </>
        }
      >
        <Segmented<StatusFilter>
          value={status}
          onChange={setStatus}
          options={[
            { value: "all", label: "All", count: all.length },
            { value: "open", label: "Open", count: counts("open") },
            { value: "confirmed", label: "Confirmed", count: counts("confirmed") },
            { value: "dismissed", label: "Dismissed", count: counts("dismissed") },
          ]}
        />
        <SearchInput value={q} onChange={setQ} placeholder="Ring number, name or account" className="w-full sm:w-64" />
      </FilterBar>

      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<RingListItem>
          rows={rows}
          loading={rings.loading}
          rowKey={(r) => r.id}
          onRowClick={(r) => router.push(`/network/rings/${r.id}`)}
          initialSort={{ key: "score", dir: "desc" }}
          empty={
            all.length ? (
              <EmptyState title="No rings match these filters" description="Clear a filter to see more." />
            ) : (
              <EmptyState
                icon={Network}
                title="No rings yet"
                description="Import the bank's transfer records on the Data & bank page, or load demo data."
                action={
                  <Button icon={Database} onClick={() => router.push("/network/ops")}>
                    Import data
                  </Button>
                }
              />
            )
          }
          columns={[
            { key: "id", header: "Ring", sort: (r) => r.number ?? 0, render: (r) => <span className="whitespace-nowrap font-medium">{ringName(r)}</span> },
            { key: "score", header: "Risk", sort: (r) => r.score, render: (r) => <RiskScore value={r.score} /> },
            { key: "size", header: "Accounts", align: "right", sort: (r) => r.size, render: (r) => r.size },
            { key: "victims", header: "People who paid in", align: "right", sort: (r) => r.possible_victims, hideBelow: "xl", render: (r) => r.possible_victims },
            { key: "inflow", header: "Money paid in", align: "right", sort: (r) => r.victim_inflow, render: (r) => naira(r.victim_inflow) },
            { key: "cash", header: "Taken out as cash", align: "right", sort: (r) => r.cash_out_total, hideBelow: "2xl", render: (r) => naira(r.cash_out_total) },
            {
              key: "typ",
              header: "Warning signs",
              hideBelow: "lg",
              render: (r) => (
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="text-[13px]">{TYPOLOGY[Object.keys(r.typologies)[0]] ?? Object.keys(r.typologies)[0]}</span>
                  {Object.keys(r.typologies).length > 1 && (
                    <span className="text-xs text-[var(--muted)]" title={Object.keys(r.typologies).map((k) => TYPOLOGY[k] ?? k).join(", ")}>
                      and {Object.keys(r.typologies).length - 1} more
                    </span>
                  )}
                </div>
              ),
            },
            { key: "last", header: "Last activity", sort: (r) => r.last_seen ?? "", hideBelow: "md", render: (r) => <span className="whitespace-nowrap text-xs text-[var(--muted)]">{fmtDay(r.last_seen)}</span> },
            { key: "status", header: "Status", sort: (r) => r.status, render: (r) => { const st = pick(RING_STATUS, r.status); return <Badge tone={st.tone} icon={st.icon}>{st.label}</Badge>; } },
          ]}
        />
      </div>

      <ConfirmDialog
        open={confirmSim}
        onCancel={() => setConfirmSim(false)}
        title="Replace all data with demo data?"
        message="This deletes every account, payment, ring and alert, then creates a made-up Nigerian bank with five hidden mule rings for TheOne to find."
        confirmLabel="Load demo data"
        danger
        busy={busy === "sim"}
        onConfirm={() =>
          run("sim", async () => {
            const r = await net.simulate(Math.floor(Math.random() * 10_000), 600, 5);
            setConfirmSim(false);
            reloadAll();
            toast.success("Demo data loaded", `${r.generated.accounts.toLocaleString()} accounts and ${r.generated.transfers.toLocaleString()} payments`);
          })
        }
      />
    </>
  );
}
