"use client";

/** Learned rule weights from confirmed outcomes, and the shadow risk model. */

import { Brain } from "lucide-react";
import { useState } from "react";
import { Badge, Button, DataTable, EmptyState, InlineError, Kpi, KpiStrip, riskLevel, Section, useToast } from "@/presentation/components/ui";
import { fmtDate, pct } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { TYPOLOGY } from "@/presentation/status";
import type { LearningRow } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

export function ModelSection() {
  const net = useNetwork();
  const toast = useToast();
  const data = useAsync(() => net.model());
  const [busy, setBusy] = useState(false);
  const d = data.data;
  const simulated = !!d?.labels && Object.keys(d.labels.sources).every((k) => k === "simulation");
  const ev = d?.evaluation;
  const fmt = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

  async function train() {
    setBusy(true);
    try {
      const r = await net.trainModel();
      toast.success("Learning done", `From ${r.labels?.mule} mule and ${r.labels?.legit} genuine accounts.`);
      data.reload();
    } catch (e) {
      toast.error("Could not learn", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="Learning model (in testing)"
      description="A model that learns from confirmed cases runs alongside the warning signs. It never decides anything; it only shows where it agrees and where it would look elsewhere."
      actions={<Button variant="primary" icon={Brain} loading={busy} onClick={train}>{d?.trained ? "Learn again" : "Start learning"}</Button>}
      flush
    >
      <InlineError error={data.error} onRetry={data.reload} />
      {d && !d.trained && (
        <EmptyState icon={Brain} title="Not started yet" description={`It needs at least ${d.min_each} confirmed mule accounts and ${d.min_each} confirmed genuine accounts to learn from.`} />
      )}
      {d?.trained && ev && (
        <>
          {simulated && (
            <div className="border-b border-[var(--line)] bg-[var(--warning-soft)] px-4 py-3 text-sm sm:px-6 lg:px-8">
              It learned from demo data, where the mule patterns are planted on purpose, so near-perfect scores here only show that it works.
              Real proof needs confirmed cases from a trial at the bank.
            </div>
          )}
          <KpiStrip cols={4}>
            <Kpi label="Cases learned from" value={(d.labels?.mule ?? 0) + (d.labels?.legit ?? 0)} sub={`${d.labels?.mule} mules · ${d.labels?.legit} genuine`} />
            <Kpi label="How well it sorts risky from safe" value={fmt(ev.model.auc)} sub={`warning signs ${fmt(ev.rules.auc)} · 1.00 is perfect`} />
            <Kpi label="Mules caught" value={pct(ev.model.recall)} sub={`warning signs ${pct(ev.rules.recall)}`} />
            <Kpi label="Agrees with the warning signs" value={pct(d.disagreements?.agreement)} sub={`on ${d.disagreements?.accounts ?? 0} accounts`} />
          </KpiStrip>
          <div className="grid lg:grid-cols-2 lg:divide-x lg:divide-[var(--line)]">
            <div>
              <h3 className="border-b border-[var(--line)] px-4 py-3 text-sm font-semibold text-[var(--ink)] sm:px-6 lg:px-8">What the model weighs most</h3>
              <ul className="divide-y divide-[var(--line)]">
                {d.top_features?.map((f) => (
                  <li key={f.feature} className="flex items-center gap-3 px-4 py-2.5 text-sm sm:px-6 lg:px-8">
                    <span className="min-w-0 flex-1">{f.feature.charAt(0).toUpperCase() + f.feature.slice(1)}</span>
                    <Badge tone={f.weight > 0 ? "serious" : "good"}>{f.direction}</Badge>
                  </li>
                ))}
              </ul>
            </div>
            <div className="border-t border-[var(--line)] lg:border-t-0">
              <h3 className="border-b border-[var(--line)] px-4 py-3 text-sm font-semibold text-[var(--ink)] sm:px-6 lg:px-8">Where they disagree</h3>
              {!d.disagreements?.model_only.length && !d.disagreements?.rules_only.length ? (
                <p className="px-4 py-4 text-sm text-[var(--muted)] sm:px-6 lg:px-8">No strong disagreements. Both flag the same accounts.</p>
              ) : (
                <ul className="divide-y divide-[var(--line)]">
                  {[...(d.disagreements?.model_only ?? []).map((x) => ({ ...x, side: "The model sees risk the warning signs miss" })),
                    ...(d.disagreements?.rules_only ?? []).map((x) => ({ ...x, side: "Warning signs flag it, the model does not" }))].map((x) => (
                    <li key={x.account_id + x.side} className="px-4 py-2.5 text-sm sm:px-6 lg:px-8">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{x.name || x.account_no}</span>
                        <span className="text-xs text-[var(--muted)]">model: {riskLevel(x.model).label.toLowerCase()} risk · warning signs: {riskLevel(x.rules).label.toLowerCase()} risk</span>
                      </div>
                      <div className="text-xs text-[var(--muted)]">{x.side}{x.because.length ? `: ${x.because.join(", ")}` : ""}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <p className="border-t border-[var(--line)] px-4 py-3 text-xs text-[var(--muted)] sm:px-6 lg:px-8">
            Last learned {d.trained_at ? fmtDate(d.trained_at) : ""}. It is tested on cases it did not learn from, and never sees your team&apos;s decisions, so it cannot simply copy them.
          </p>
        </>
      )}
    </Section>
  );
}

export function LearningTab() {
  const net = useNetwork();
  const toast = useToast();
  const data = useAsync(() => net.learning());
  const [busy, setBusy] = useState(false);
  const d = data.data;

  async function refresh() {
    setBusy(true);
    try {
      const r = await net.refreshLearning();
      toast.success("Updated", `${r.updated.length} warning signs adjusted. ${r.skipped_low_samples.length} have too few cases yet.`);
      data.reload();
    } catch (e) {
      toast.error("Could not update", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title="How much each warning sign counts"
      description={`Once a warning sign has at least ${d?.min_samples ?? 5} confirmed cases, TheOne adjusts how much it counts: from a quarter as much to twice as much. No single sign can flag an account on its own. Fraud reports and your team's confirmations always count fully.`}
      actions={<Button variant="primary" icon={Brain} loading={busy} onClick={refresh} disabled={d ? !d.enabled : false}>Update from confirmed cases</Button>}
      flush
    >
      <InlineError error={data.error} onRetry={data.reload} />
      {d && !d.enabled && <div className="border-b border-[var(--line)] bg-[var(--warning-soft)] px-4 py-3 text-sm sm:px-6 lg:px-8">Learning is switched off on this server. The hand-set weights are in use.</div>}
      <DataTable<LearningRow>
        rows={d?.candidates ?? []}
        loading={data.loading}
        rowKey={(r) => r.code}
        initialSort={{ key: "mule", dir: "desc" }}
        empty={<EmptyState icon={Brain} title="No outcomes yet" description="Confirm or dismiss rings, or import labels, then update." />}
        columns={[
          { key: "code", header: "Warning sign", sort: (r) => TYPOLOGY[r.code] ?? r.code, render: (r) => <span className="font-medium">{TYPOLOGY[r.code] ?? r.code}</span> },
          { key: "mule", header: "On mules", align: "right", sort: (r) => r.mule, render: (r) => r.mule },
          { key: "legit", header: "On genuine accounts", align: "right", sort: (r) => r.legit, render: (r) => r.legit },
          { key: "prior", header: "Starting value", align: "right", hideBelow: "sm", render: (r) => r.prior.toFixed(2) },
          { key: "learned", header: "Learned value", align: "right", hideBelow: "sm", render: (r) => <span className="font-medium">{r.learned.toFixed(2)}</span> },
          {
            key: "use",
            header: "In use",
            align: "right",
            render: (r) => {
              const a = d?.applied[r.code];
              if (r.exempt) return <Badge>Direct evidence, fixed</Badge>;
              if (a) return <Badge tone={a.multiplier < 1 ? "warning" : "good"}>×{a.multiplier.toFixed(2)}{a.capped ? ", capped" : ""}</Badge>;
              return r.active ? <Badge tone="info">Ready to update</Badge> : <Badge>Too few cases</Badge>;
            },
          },
        ]}
      />
    </Section>
  );
}
