"use client";

import { AlertOctagon, CheckCircle2, Cpu, Landmark, PlayCircle, Sparkles, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, DetailList, Field, InlineError, Input, PageHeader, riskLevel, Section, useToast } from "@/presentation/components/ui";
import { fmtDate } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { useActor } from "@/presentation/hooks/useActor";
import { useAssistant, useDocuments, useIdentity, useNetwork } from "@/presentation/hooks/gateways";

const on = (yes: boolean, label: string, off = "Not connected") => (
  <Badge tone={yes ? "good" : "neutral"} icon={yes ? CheckCircle2 : undefined}>{yes ? label : off}</Badge>
);

export function SettingsPage() {
  const router = useRouter();
  const api = useIdentity();
  const assistantApi = useAssistant();
  const documents = useDocuments();
  const net = useNetwork();
  const toast = useToast();
  const summary = useAsync(() => net.summary());
  const health = useAsync(() => api.health());
  const assistant = useAsync(() => assistantApi.status());
  const [actor, setActor] = useActor();
  const [name, setName] = useState(actor);
  const s = summary.data;
  const h = health.data;
  const a = assistant.data;

  const level = (v: number) => `${riskLevel(v).label.toLowerCase()} risk (${Math.round(v * 100)} out of 100)`;
  const fast = s ? (s.thresholds.fast_window_min >= 60 ? `${s.thresholds.fast_window_min / 60} hour${s.thresholds.fast_window_min === 60 ? "" : "s"}` : `${s.thresholds.fast_window_min} minutes`) : "";

  return (
    <>
      <PageHeader title="Settings" subtitle="How TheOne is set up for your bank, and your name for the record." />
      <InlineError error={summary.error || health.error} onRetry={() => { summary.reload(); health.reload(); }} />

      <Section title="You" description="Shown on everything you do, so the record says who did what. Saved in this browser only.">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Your name" className="w-full sm:w-72">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Button variant="primary" icon={UserRound} disabled={!name.trim() || name.trim() === actor}
            onClick={() => { setActor(name.trim()); toast.success("Saved", `Your actions will show as ${name.trim()}.`); }}>
            Save
          </Button>
        </div>
      </Section>

      <Section title="How it works" description="A short animated story: a scam payment, and how TheOne stops it before the money leaves the bank.">
        <Button icon={PlayCircle} onClick={() => router.push("/simulation")}>Watch how it works</Button>
      </Section>

      <Section title="How TheOne works here" description="What it checks, and when it steps in." flush>
        <DetailList
          page
          items={[
            { label: "Mode", value: s ? <Badge tone={s.mode === "shadow" ? "warning" : "good"}>{s.mode === "shadow" ? "Test mode: TheOne checks and records, nothing is sent to the bank" : "Live: holds and blocks are sent to the bank"}</Badge> : "–" },
            { label: "Last checked", value: s ? fmtDate(s.computed_at) : "–" },
            { label: "What it looks at", value: s ? `${s.transfers_in_window.toLocaleString()} payments from the last ${s.window_days} days, across ${s.accounts.toLocaleString()} accounts` : "–" },
            { label: "Flags an account at", value: s ? level(s.thresholds.flag) : "–" },
            { label: "Holds a payment at", value: s ? level(s.thresholds.hold) : "–" },
            { label: "“Moved on quickly” means", value: s ? `within ${fast} (the same or next day for statements)` : "–" },
            { label: "Learns from confirmed cases", value: s ? (s.learning_enabled ? "On" : "Off") : "–" },
            { label: "Demo data", value: s ? (s.simulation_enabled ? <Badge tone="warning">Allowed on this server</Badge> : "Not allowed") : "–" },
          ]}
        />
      </Section>

      <Section title="Connections" description="Who TheOne talks to." flush>
        <DetailList
          page
          items={[
            { label: "Our bank", value: s ? s.home_bank.name : "–" },
            { label: "Bank systems", value: s ? (s.bank_connector === "none" ? on(false, "", "Not connected: holds and blocks are done by hand") : on(true, "Connected")) : "–" },
            { label: "Other banks (through NIBSS)", value: s ? (s.nibss_connector === "none" ? on(false, "", "Not connected: TheOne cannot follow money into other banks") : on(true, s.simulation_enabled ? "Connected (practice version on this server)" : "Connected")) : "–" },
            { label: "Assistant", value: a ? on(a.enabled, "On", "Off") : "–" },
          ]}
        />
      </Section>

      <details className="group border-b border-[var(--line)] bg-[var(--surface)]">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-4 text-sm font-semibold sm:px-6 lg:px-8">
          Technical details
          <span className="text-xs font-normal text-[var(--muted)] group-open:hidden">Show</span>
          <span className="hidden text-xs font-normal text-[var(--muted)] group-open:inline">Hide</span>
        </summary>
        <DetailList
          page
          items={[
            { label: "Last analysis", value: s ? `${s.analysis_mode} · ${Math.round(s.duration_ms)} ms` : "–" },
            { label: "Ring members from", value: s ? `risk ${s.thresholds.ring_min.toFixed(2)}` : "–" },
            { label: "Learned rule weights", value: s ? s.learned_rules : "–" },
            { label: "Bank code", value: s ? s.home_bank.code : "–" },
            { label: "Bank connector", value: s ? (s.bank_connector === "none" ? "none" : <span className="inline-flex items-center gap-2"><Landmark className="size-4 text-[var(--muted)]" />{s.bank_connector.toUpperCase()} (Open Banking Nigeria)</span>) : "–" },
            { label: "Assistant models", value: a?.enabled ? <span className="inline-flex flex-wrap items-center gap-2"><Sparkles className="size-4 text-[var(--muted)]" />Gemini · voice {a.live_model} · text {a.text_model}</span> : "–" },
            { label: "Voice model", value: h ? <span className="inline-flex items-center gap-2"><Cpu className="size-4 text-[var(--muted)]" />{h.embedder.replace("sherpa-onnx:", "").replace(".onnx", "")}</span> : "–" },
            { label: "Voice match accepted at", value: h ? `${h.thresholds.match_accept} · extra check from ${h.thresholds.match_stepup}` : "–" },
            { label: "Fake-voice detection", value: h ? <span className="inline-flex flex-wrap items-center gap-2">{h.antispoof}<Badge tone="warning" icon={AlertOctagon}>Basic version, to be replaced</Badge></span> : "–" },
            { label: "Audio formats", value: h ? h.accepted_formats.join(", ") : "–" },
            { label: "Server address", value: <span className="font-mono text-xs">{documents.apiUrl}</span> },
          ]}
        />
        <p className="border-t border-[var(--line)] px-4 py-3 text-xs text-[var(--muted)] sm:px-6 lg:px-8">
          These come from the server&apos;s configuration. Changing them needs a restart of the backend.
        </p>
      </details>
    </>
  );
}
