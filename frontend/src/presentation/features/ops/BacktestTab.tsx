"use client";

/** Replay past days to measure what detection would have caught, and when. */

import { FlaskConical } from "lucide-react";
import { useState } from "react";
import { Badge, Button, DataTable, EmptyState, Field, Input, Kpi, KpiStrip, Section, useToast } from "@/presentation/components/ui";
import { pct } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { TYPOLOGY } from "@/presentation/status";
import type { Backtest } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

export function BacktestTab() {
  const net = useNetwork();
  const toast = useToast();
  const labels = useAsync(() => net.labelsSummary());
  const [days, setDays] = useState("28");
  const [step, setStep] = useState("12");
  const [capacity, setCapacity] = useState("20");
  const [bt, setBt] = useState<Backtest | null>(null);
  const [busy, setBusy] = useState(false);
  const count = (lab: string) => Object.values(labels.data?.by_label[lab] ?? {}).reduce((a, b) => a + b, 0);
  const digits = (v: string) => v.replace(/\D/g, "");

  async function run() {
    setBusy(true);
    try {
      const r = await net.backtest(Number(days) || 14, Number(step) || 12, Number(capacity) || 20);
      setBt(r);
      toast.success("Replay finished", `${r.window.checkpoints} checks replayed in ${r.duration_s} seconds.`);
    } catch (e) {
      toast.error("Replay failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Section
        title="Replay the past"
        description={
          <>
            Goes back over past days as if TheOne had been running then, and compares what it would have flagged with the mule accounts the bank later confirmed.
            {labels.data && ` ${count("mule")} confirmed mules and ${count("legit")} confirmed genuine accounts are on file.`}
          </>
        }
      >
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Days back" className="w-28"><Input inputMode="numeric" value={days} onChange={(e) => setDays(digits(e.target.value))} /></Field>
          <Field label="Check every (hours)" className="w-44"><Input inputMode="numeric" value={step} onChange={(e) => setStep(digits(e.target.value))} /></Field>
          <Field label="Cases your team can review a day" className="w-56"><Input inputMode="numeric" value={capacity} onChange={(e) => setCapacity(digits(e.target.value))} /></Field>
          <Button variant="primary" icon={FlaskConical} loading={busy} onClick={run}>Replay</Button>
        </div>
      </Section>
      {!bt && !busy && <Section><EmptyState icon={FlaskConical} title="Not replayed yet" description="Replay the past to see how many confirmed mules TheOne would have caught, and how early." /></Section>}
      {bt && (
        <>
          <KpiStrip cols={4}>
            <Kpi label="Confirmed mules caught" value={pct(bt.recall)} sub={`${bt.labels.mules - bt.missed_mules} of ${bt.labels.mules}`} />
            <Kpi label="Caught before confirmation" value={bt.caught_before_confirmation} sub={bt.median_lead_hours != null ? `Median ${bt.median_lead_hours} h earlier${bt.lead_time_cases != null ? `, ${bt.lead_time_cases} cases` : ""}` : "No cases inside the window"} />
            <Kpi label="Cases worth reviewing" value={pct(bt.precision_at_capacity)} sub={`real mules, at ${bt.window.capacity_per_day} reviews a day`} />
            <Kpi label="Genuine accounts flagged by mistake" value={bt.legit_flagged} sub={`${bt.flagged_unlabelled} flagged and not yet checked`} />
          </KpiStrip>
          <KpiStrip cols={3}>
            <Kpi label="New cases a day" value={bt.alerts_per_day} />
            <Kpi label="Already flagged on day one" value={bt.already_flagged_at_start ?? "–"} sub="not counted in how early" />
            <Kpi label="Replay took" value={`${bt.duration_s} seconds`} sub={`${bt.window.checkpoints} checks`} />
          </KpiStrip>
          <Section title="Warning signs on flagged accounts" flush description="A warning sign that often shows on genuine accounts may need adjusting.">
            <DataTable
              rows={Object.entries(bt.typologies).map(([code, v]) => ({ code, ...v }))}
              rowKey={(r) => r.code}
              initialSort={{ key: "mule", dir: "desc" }}
              columns={[
                { key: "code", header: "Rule", sort: (r) => TYPOLOGY[r.code] ?? r.code, render: (r) => <span className="font-medium">{TYPOLOGY[r.code] ?? r.code}</span> },
                { key: "mule", header: "On mules", align: "right", sort: (r) => r.mule, render: (r) => r.mule },
                { key: "legit", header: "On genuine accounts", align: "right", sort: (r) => r.legit, render: (r) => (r.legit ? <Badge tone="critical">{r.legit}</Badge> : 0) },
                { key: "un", header: "Not yet checked", align: "right", sort: (r) => r.unlabelled, render: (r) => r.unlabelled },
              ]}
            />
          </Section>
        </>
      )}
    </>
  );
}
