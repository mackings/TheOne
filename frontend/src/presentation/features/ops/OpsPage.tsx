"use client";

import { FileSearch, FileUp, FlaskConical, Landmark } from "lucide-react";
import { useState } from "react";
import { InlineError, Kpi, KpiStrip, PageHeader, Section, Tabs } from "@/presentation/components/ui";
import { pct } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { BacktestTab } from "./BacktestTab";
import { BankTab } from "./BankTab";
import { ImportTab } from "./ImportTab";
import { LearningTab, ModelSection } from "./LearningTab";
import { StatementTab } from "./StatementTab";
import { useNetwork } from "@/presentation/hooks/gateways";

type Tab = "import" | "statement" | "bank" | "quality";

export function OpsPage() {
  const net = useNetwork();
  const [tab, setTab] = useState<Tab>("import");
  const summary = useAsync(() => net.summary());
  return (
    <>
      <PageHeader title="Data & bank" subtitle="Bring in the bank's records, check a statement, and see what was sent to the bank." />
      <InlineError error={summary.error} onRetry={summary.reload} />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "import", label: "Import data", icon: FileUp },
          { value: "statement", label: "Check a statement", icon: FileSearch },
          { value: "bank", label: "Sent to the bank", icon: Landmark },
          { value: "quality", label: "How well it works", icon: FlaskConical },
        ]}
      />
      {tab === "import" && <ImportTab onDone={summary.reload} />}
      {tab === "statement" && <StatementTab />}
      {tab === "bank" && <BankTab />}
      {tab === "quality" && (
        <>
          {summary.data?.has_synthetic_labels && <DemoCheck />}
          <BacktestTab />
          <LearningTab />
          <ModelSection />
        </>
      )}
    </>
  );
}

/** On demo data the hidden rings are known, so show how many TheOne found. */
function DemoCheck() {
  const net = useNetwork();
  const ev = useAsync(() => net.evaluation().catch(() => null));
  const e = ev.data;
  if (!e) return null;
  return (
    <Section title="Demo data check" description="The demo data has mule rings hidden in it on purpose. This is how many TheOne found on its own.">
      <KpiStrip cols={3}>
        <Kpi label="Hidden rings found" value={`${e.planted_rings_found} of ${e.planted_rings}`} />
        <Kpi label="Flagged accounts that really were mules" value={pct(e.precision)} />
        <Kpi label="Mules TheOne caught" value={pct(e.recall)} sub={`${e.true_positives} of ${e.mules}`} />
      </KpiStrip>
    </Section>
  );
}
