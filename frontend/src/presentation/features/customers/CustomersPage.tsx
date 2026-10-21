"use client";

import { AudioLines, Eye, Mic, ScanEye, Trash2, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  DetailList,
  Drawer,
  EmptyState,
  FilterBar,
  InlineError,
  PageHeader,
  SearchInput,
  Segmented,
  Select,
  useToast,
} from "@/presentation/components/ui";
import { fmtDate, fmtDay, timeAgo } from "@/presentation/format";
import { useAsync } from "@/presentation/hooks/useAsync";

import { DECISION, pick } from "@/presentation/status";
import type { Customer } from "@/domain/identity";
import { useIdentity } from "@/presentation/hooks/gateways";

const LANG: Record<string, string> = { en: "English", pcm: "Pidgin", yo: "Yoruba", ig: "Igbo", ha: "Hausa" };
type Enrol = "all" | "both" | "voice" | "iris" | "none";

export function CustomersPage() {
  const api = useIdentity();
  const list = useAsync(() => api.listCustomers());
  const all = useMemo(() => list.data ?? [], [list.data]);
  const [enrol, setEnrol] = useState<Enrol>("all");
  const [lang, setLang] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Customer | null>(null);

  const match = (c: Customer, e: Enrol) =>
    e === "all" || (e === "both" && c.enrolled && c.iris_enrolled) || (e === "voice" && c.enrolled) || (e === "iris" && c.iris_enrolled) || (e === "none" && !c.enrolled && !c.iris_enrolled);
  const needle = q.trim().toLowerCase();
  const rows = all.filter((c) => match(c, enrol) && (!lang || c.language === lang) && (!needle || `${c.display_name} ${c.external_id ?? ""} ${c.id}`.toLowerCase().includes(needle)));
  const langs = [...new Set(all.map((c) => c.language))].sort();

  return (
    <>
      <PageHeader
        title="Customers"
        subtitle="Customers who can confirm a payment is really them, with their voice or an eye scan (iris)."
        actions={
          <Link href="/enrol">
            <Button variant="primary" icon={UserPlus}>Add a customer</Button>
          </Link>
        }
      />
      <InlineError error={list.error} onRetry={list.reload} />
      <FilterBar
        active={lang ? 1 : 0}
        more={<Select value={lang} onChange={(e) => setLang(e.target.value)} className="w-44" aria-label="Language" options={[{ value: "", label: "Any language" }, ...langs.map((l) => ({ value: l, label: LANG[l] ?? l.toUpperCase() }))]} />}
      >
        <Segmented<Enrol>
          value={enrol}
          onChange={setEnrol}
          options={[
            { value: "all", label: "All", count: all.length },
            { value: "both", label: "Voice and iris", count: all.filter((c) => match(c, "both")).length },
            { value: "voice", label: "Voice", count: all.filter((c) => c.enrolled).length },
            { value: "iris", label: "Iris", count: all.filter((c) => c.iris_enrolled).length },
            { value: "none", label: "Not set up", count: all.filter((c) => match(c, "none")).length },
          ]}
        />
        <SearchInput value={q} onChange={setQ} placeholder="Name or reference" className="w-full sm:w-56" />
      </FilterBar>
      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        <DataTable<Customer>
          rows={rows}
          loading={list.loading}
          rowKey={(c) => c.id}
          onRowClick={setOpen}
          selectedKey={open?.id}
          initialSort={{ key: "created", dir: "desc" }}
          empty={
            <EmptyState
              icon={Users}
              title={all.length ? "No customers match these filters" : "No customers yet"}
              description={all.length ? "Clear the search or choose “All”." : "Add a customer and record their voice to start."}
              action={!all.length && <Link href="/enrol"><Button variant="primary" icon={UserPlus}>Add a customer</Button></Link>}
            />
          }
          columns={[
            {
              key: "name",
              header: "Customer",
              sort: (c) => c.display_name.toLowerCase(),
              render: (c) => (
                <div className="min-w-0">
                  <div className="font-medium">{c.display_name}</div>
                  {c.external_id && <div className="text-xs text-[var(--muted)]">Ref {c.external_id}</div>}
                </div>
              ),
            },
            { key: "lang", header: "Language", hideBelow: "sm", sort: (c) => c.language, render: (c) => LANG[c.language] ?? c.language.toUpperCase() },
            {
              key: "voice",
              header: "Voice",
              sort: (c) => (c.enrolled ? c.template?.consistency ?? 0 : -1),
              render: (c) => (c.enrolled ? <Badge tone="good" icon={AudioLines}>Set up</Badge> : <Badge>Not set up</Badge>),
            },
            {
              key: "iris",
              header: "Iris (eye scan)",
              sort: (c) => (c.iris_enrolled ? 1 : 0),
              render: (c) => (c.iris_enrolled ? <Badge tone="good" icon={Eye}>Set up</Badge> : <Badge>Not set up</Badge>),
            },
            { key: "created", header: "Added", align: "right", hideBelow: "md", sort: (c) => c.created_at, render: (c) => <span className="whitespace-nowrap text-xs">{fmtDay(c.created_at)}</span> },
          ]}
        />
      </div>
      {open && (
        <CustomerDrawer
          customer={open}
          onClose={() => setOpen(null)}
          onChanged={(c) => {
            setOpen(c);
            list.reload();
          }}
        />
      )}
    </>
  );
}

const MODALITY: Record<string, string> = { voice: "Voice", iris: "Iris", device: "Phone fingerprint" };

function CustomerDrawer({ customer: c, onClose, onChanged }: { customer: Customer; onClose: () => void; onChanged: (c: Customer | null) => void }) {
  const api = useIdentity();
  const toast = useToast();
  const events = useAsync(() => api.listEvents(c.id), [c.id]);
  const [revoke, setRevoke] = useState<"voice" | "iris" | null>(null);
  const [busy, setBusy] = useState(false);
  const ev = events.data ?? [];

  async function doRevoke() {
    if (!revoke) return;
    setBusy(true);
    try {
      if (revoke === "voice") await api.revokeTemplate(c.id);
      else await api.revokeIrisTemplate(c.id);
      toast.success(`${revoke === "voice" ? "Voice" : "Iris"} removed`, `${c.display_name} must set it up again to use it.`);
      onChanged(revoke === "voice" ? { ...c, enrolled: false, template: null } : { ...c, iris_enrolled: false, iris_template: null });
      setRevoke(null);
    } catch (e) {
      toast.error("Could not remove it", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      wide
      title={c.display_name}
      subtitle={`${LANG[c.language] ?? c.language} · added ${fmtDate(c.created_at)}`}
      footer={
        <>
          {c.enrolled && <Link href={`/verify?customer=${c.id}`}><Button icon={Mic}>Check voice</Button></Link>}
          <Link href={`/iris?customer=${c.id}&mode=${c.iris_enrolled ? "verify" : "enrol"}`}>
            <Button icon={ScanEye} variant={c.iris_enrolled ? "secondary" : "primary"}>{c.iris_enrolled ? "Check iris" : "Set up iris"}</Button>
          </Link>
        </>
      }
    >
      <DetailList
        items={[
          { label: "Bank reference", value: c.external_id ?? "–" },
          {
            label: "Voice",
            value: c.template ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="good" icon={AudioLines}>Set up</Badge>
                <span className="text-xs text-[var(--muted)]">from {c.template.sample_count} recorded phrases</span>
              </div>
            ) : (
              <Badge>Not set up</Badge>
            ),
          },
          {
            label: "Iris (eye scan)",
            value: c.iris_template ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="good" icon={Eye}>Set up</Badge>
                <span className="text-xs text-[var(--muted)]">from {c.iris_template.sample_count} eye images</span>
              </div>
            ) : (
              <Badge>Not set up</Badge>
            ),
          },
        ]}
      />
      {(c.enrolled || c.iris_enrolled) && (
        <div className="flex flex-wrap gap-2 border-y border-[var(--line)] bg-[var(--surface-2)] px-5 py-3">
          {c.enrolled && <Button size="sm" variant="ghost" icon={Trash2} className="text-[var(--critical)]" onClick={() => setRevoke("voice")}>Remove voice</Button>}
          {c.iris_enrolled && <Button size="sm" variant="ghost" icon={Trash2} className="text-[var(--critical)]" onClick={() => setRevoke("iris")}>Remove iris</Button>}
        </div>
      )}
      <div className="px-5 pb-2 pt-5 text-sm font-semibold text-[var(--ink)]">Checks so far</div>
      <InlineError error={events.error} onRetry={events.reload} />
      {!events.loading && !ev.length ? (
        <EmptyState icon={AudioLines} title="No checks yet" />
      ) : (
        <ul className="divide-y divide-[var(--line)] border-t border-[var(--line)]">
          {events.loading && !ev.length
            ? Array.from({ length: 4 }).map((_, i) => (
                <li key={i} className="px-5 py-3">
                  <div className="skeleton h-3.5 w-2/3 rounded" />
                </li>
              ))
            : ev.map((e) => {
                const d = pick(DECISION, e.decision);
                return (
                  <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 text-sm">
                    <Badge tone={d.tone} icon={d.icon}>{d.label}</Badge>
                    <span className="font-medium">{MODALITY[e.modality] ?? e.modality} check{e.resolves_event_id ? ", to confirm a payment" : ""}</span>
                    <span className="text-[var(--muted)]">{e.context ? e.context.replace(/_/g, " ") : "login"}{e.continuous_session_id ? " · during a call" : ""}</span>
                    <span className="w-full text-xs text-[var(--muted)]" title={fmtDate(e.created_at)}>{timeAgo(e.created_at)}{e.reasons.length ? ` · ${e.reasons.join("; ")}` : ""}</span>
                  </li>
                );
              })}
        </ul>
      )}
      <ConfirmDialog
        open={revoke != null}
        onCancel={() => setRevoke(null)}
        onConfirm={doRevoke}
        busy={busy}
        danger
        title={`Remove ${c.display_name}'s ${revoke === "iris" ? "iris" : "voice"}?`}
        message={`Their saved ${revoke === "iris" ? "eye scan" : "voice"} is deleted for good. Until they set it up again, the bank's one-time code is used instead.`}
        confirmLabel="Remove"
      />
    </Drawer>
  );
}
