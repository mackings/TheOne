"use client";

import { AudioLines, Check, Maximize2, Copy, FileSearch, FileText, History, Lightbulb, ListChecks, Network, Route, Users, XCircle } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  Field,
  InlineError,
  Input,
  Kpi,
  KpiStrip,
  PageHeader,
  RiskScore,
  Section,
  Tabs,
  useToast,
} from "@/presentation/components/ui";

import { fmtDay, naira, ringName } from "@/presentation/format";
import { useActor } from "@/presentation/hooks/useActor";
import { useAsync } from "@/presentation/hooks/useAsync";
import { pick, RING_STATUS } from "@/presentation/status";
import { type PlanAction, ringStory } from "./explain";
import { AccountDrawer } from "./ring/AccountDrawer";
import { MoneyMapFullscreen } from "./ring/MoneyMapFullscreen";
import { type Act, ACT_COPY, findingsOf } from "./ring/copy";
import { RingAccounts } from "./ring/RingAccounts";
import { RingActivity } from "./ring/RingActivity";
import { RingEvidence } from "./ring/RingEvidence";
import { RingGraph } from "./RingGraph";
import { RingNextSteps } from "./ring/RingNextSteps";
import { RingSummary } from "./ring/RingSummary";
import { useDocuments, useNetwork } from "@/presentation/hooks/gateways";
import { useZiva } from "@/presentation/features/ziva/ZivaProvider";
import { useZivaSpotlight } from "@/presentation/features/ziva/useZivaSpotlight";

type Tab = "summary" | "flow" | "evidence" | "accounts" | "activity" | "next";

export function RingView() {
  const documents = useDocuments();
  const net = useNetwork();
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const [actor, setActor] = useActor();
  const ring = useAsync(() => net.ring(id), [id]);
  const [selected, setSelected] = useState<string | null>(null);
  // The account Ziva is talking about: lit on the map, without opening its panel.
  const [spotlight, setSpotlight] = useState<string | null>(null);
  const ziva = useZiva();
  const [tab, setTab] = useState<Tab>("summary");
  const [big, setBig] = useState(false);
  const [details, setDetails] = useState(false);
  const [tracing, setTracing] = useState(false);
  const [copied, setCopied] = useState(false);
  function chooseAccount(id: string | null) {
    setSelected(id);
    setSpotlight(null);
  }
  function copyNumber(text: string) {
    navigator.clipboard?.writeText(text).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      },
      () => toast.error("Could not copy", "Select the number and copy it instead."),
    );
  }
  const [confirmTrace, setConfirmTrace] = useState(false);
  const router = useRouter();
  const traces = useAsync(() => net.ringTraces(id), [id]);

  async function trace() {
    if (!r) return;
    setTracing(true);
    try {
      const out = await net.traceRing(r.id, actor || "analyst");
      setConfirmTrace(false);
      const failed = out.requests.filter((x) => x.status === "failed");
      if (failed.length === out.requests.length && failed.length)
        toast.error("The other banks did not answer", failed[0].error ?? "Try again later.");
      else if (!out.requests.length) toast.info("Nothing to follow", "No money from this ring went to another bank.");
      else
        toast.success(`${out.accounts_traced} bank account${out.accounts_traced > 1 ? "s" : ""} answered`,
          `${naira(out.amount_followed)} followed to ${out.new_accounts} new account${out.new_accounts === 1 ? "" : "s"}${out.cash_found ? `, ${naira(out.cash_found)} of it withdrawn as cash` : ""}.`);
      traces.reload();
      if (out.ring_id !== r.id) router.replace(`/network/rings/${out.ring_id}`);
      else ring.reload();
    } catch (e) {
      toast.error("Could not ask the other banks", (e as Error).message);
    } finally {
      setTracing(false);
    }
  }
  const [act, setAct] = useState<Act>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const r = ring.data;
  const members = useMemo(() => (r ? r.nodes.filter((n) => r.summary.roles[n.id]) : []), [r]);
  useZivaSpotlight(r?.nodes, setSpotlight);
  const { focusAccount } = ziva;
  useEffect(() => focusAccount(selected), [focusAccount, selected]);
  const node = r?.nodes.find((n) => n.id === selected) ?? null;
  const st = pick(RING_STATUS, r?.status);
  const story = useMemo(() => (r ? ringStory(r) : []), [r]);
  const findings = useMemo(() => findingsOf(members), [members]);
  const openEvidence = (ringId: string) =>
    documents.open(`/network/rings/${ringId}/evidence`).catch((e) => toast.error("Could not open evidence pack", e.message));
  function onPlan(a?: PlanAction) {
    if (!r) return;
    if (a === "watchlist") setAct({ action: "watchlist_24h" });
    else if (a === "confirm") setAct({ action: "confirm" });
    else if (a === "trace") setConfirmTrace(true);
    else if (a === "evidence") openEvidence(r.id);
  }

  async function doAction() {
    if (!act || !r) return;
    setBusy(true);
    try {
      const out = await net.ringAction(r.id, act.action, actor || "analyst", act.accounts, note || undefined);
      const done = (out as { bank_actions?: { status: string }[] }).bank_actions ?? [];
      const failed = done.filter((a) => a.status === "failed").length;
      toast[failed ? "warning" : "success"](
        `${ACT_COPY[act.action].label}: ${out.accounts.length} account${out.accounts.length > 1 ? "s" : ""}`,
        done.length ? (failed ? `${failed} bank action${failed > 1 ? "s" : ""} failed; retry on Data & bank` : `${done.length} bank action${done.length > 1 ? "s" : ""} recorded`) : undefined,
      );
      setAct(null);
      setNote("");
      ring.reload();
    } catch (e) {
      toast.error("Action failed", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title={
          r ? (
            <span className="inline-flex items-center gap-2">
              {ringName(r)}
              <button
                className="inline-flex items-center gap-1 rounded-[6px] border border-[var(--line-strong)] px-2 py-1 text-xs font-medium text-[var(--ink-2)] hover:border-[var(--brand)] hover:text-[var(--brand)]"
                onClick={() => copyNumber(String(r.number ?? r.id))}
                aria-label="Copy ring number"
                title="Copy ring number"
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </span>
          ) : "Ring"
        }
        crumbs={[{ label: "Mule rings", href: "/network" }, { label: r ? ringName(r) : "…" }]}
        subtitle={r ? <span className="inline-flex flex-wrap items-center gap-2"><Badge tone={st.tone} icon={st.icon}>{st.label}</Badge><span>{fmtDay(r.summary.first_seen)} – {fmtDay(r.summary.last_seen)}</span></span> : undefined}
        actions={
          r && (
            <>
              <Button variant="ghost" icon={XCircle} disabled={r.status === "dismissed"} onClick={() => setAct({ action: "dismiss" })}>
                Not a mule ring
              </Button>
              <Button icon={FileText} onClick={() => openEvidence(r.id)}>
                Evidence pack
              </Button>
            </>
          )
        }
      />
      <InlineError error={ring.error} onRetry={ring.reload} />

      {r && (
        <>
          <KpiStrip cols={5}>
            <Kpi label="Risk" value={<RiskScore value={r.score} />} />
            <Kpi label="Accounts in the ring" value={r.summary.size} sub={`${members.filter((m) => m.home).length} at our bank`} />
            <Kpi label="People who paid in" value={r.summary.possible_victims} sub="possible victims" />
            <Kpi label="Money paid in" value={naira(r.summary.victim_inflow)} />
            <Kpi label="Taken out as cash" value={naira(r.summary.cash_out_total)} />
          </KpiStrip>

          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "summary", label: "What happened", icon: Lightbulb },
              { value: "flow", label: "Money flow", icon: Network },
              { value: "evidence", label: `Evidence (${findings.length})`, icon: FileSearch },
              { value: "accounts", label: `Accounts (${members.length})`, icon: Users },
              { value: "activity", label: "Activity", icon: History },
              { value: "next", label: "Next steps", icon: ListChecks },
            ]}
          />

          {tab === "summary" && <RingSummary r={r} story={story} />}

          {tab === "flow" && (
            <Section
              description="The money moves from left to right. Click an account to see why it was flagged, or point at it for its account number."
              actions={
                <>
                  <Button size="sm" icon={AudioLines} onClick={() => ziva.explainRing(r)}>Talk me through it</Button>
                  <Button size="sm" icon={Route} loading={tracing} onClick={() => setConfirmTrace(true)}>Follow it into other banks</Button>
                  <Button size="sm" variant="primary" icon={Maximize2} onClick={() => setBig(true)}>Enlarge</Button>
                </>
              }
            >
              <RingGraph ring={r} selected={selected ?? spotlight} onSelect={chooseAccount} />
            </Section>
          )}

          {tab === "evidence" && <RingEvidence findings={findings} onSelect={setSelected} />}
          {tab === "accounts" && <RingAccounts members={members} selected={selected} onSelect={setSelected} onAct={setAct} />}
          {tab === "activity" && <RingActivity r={r} traces={traces.data} />}
          {tab === "next" && <RingNextSteps r={r} onPlan={onPlan} />}
        </>
      )}

      {big && r && (
        <MoneyMapFullscreen ring={r} selected={selected ?? spotlight} onSelect={chooseAccount} onDetails={() => { setSelected(selected ?? spotlight); setDetails(true); }}
          onBriefing={() => ziva.explainRing(r)} onClose={() => { setBig(false); setDetails(false); }} />
      )}
      <AccountDrawer
        node={!big || details ? node : null}
        member={!!(node && r?.summary.roles[node.id])}
        onClose={() => (big ? setDetails(false) : setSelected(null))}
        onAct={setAct}
      />

      <ConfirmDialog
        open={confirmTrace}
        onCancel={() => setConfirmTrace(false)}
        onConfirm={trace}
        busy={tracing}
        title="Ask other banks where the money went?"
        message="TheOne asks each bank that received money from this ring where the money went next, and then asks once more for the banks after that. The answers are added to the money map and every request is recorded."
        confirmLabel="Ask the banks"
      >
        <Field label="Your name (kept in the record)">
          <Input value={actor} onChange={(e) => setActor(e.target.value)} />
        </Field>
      </ConfirmDialog>

      <ConfirmDialog
        open={!!act}
        onCancel={() => { setAct(null); setNote(""); }}
        onConfirm={doAction}
        busy={busy}
        title={act ? ACT_COPY[act.action].title : ""}
        message={act ? ACT_COPY[act.action].message : ""}
        confirmLabel={act ? ACT_COPY[act.action].label : ""}
        danger={act ? ACT_COPY[act.action].danger : false}
        requireText={act ? ACT_COPY[act.action].require : undefined}
      >
        <div className="grid gap-3">
          <Field label="Your name (kept in the record)">
            <Input value={actor} onChange={(e) => setActor(e.target.value)} />
          </Field>
          <Field label="Note (optional)">
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. confirmed with two victims by phone" />
          </Field>
        </div>
      </ConfirmDialog>
    </>
  );
}
