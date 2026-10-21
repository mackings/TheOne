"use client";

/** Activity tab: details shared inside the ring, what the team did, and questions sent to other banks. */
import { Ban, CheckCircle2, Fingerprint } from "lucide-react";
import { Badge, DataTable, Section } from "@/presentation/components/ui";

import { accountLine, fmtDate, naira } from "@/presentation/format";
import { ACT_COPY } from "./copy";
import type { RingDetail, TraceRow } from "@/domain/network";

export function RingActivity({ r, traces }: { r: RingDetail; traces: TraceRow[] | undefined }) {
  return (
    <>
      <div className="grid border-b border-[var(--line)] bg-[var(--surface)] lg:grid-cols-2 lg:divide-x lg:divide-[var(--line)]">
        <div>
          <h2 className="border-b border-[var(--line)] px-4 py-3 text-sm font-semibold sm:px-6 lg:px-8">Shared phones and IDs</h2>
          {r.identifier_links.length ? (
            <ul className="divide-y divide-[var(--line)]">
              {r.identifier_links.map((l, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm sm:px-6 lg:px-8">
                  <Fingerprint className="size-4 text-[var(--muted)]" />
                  <span>{l.kind === "bvn" ? "Same BVN (ID number)" : l.kind === "phone" ? "Same phone number" : l.kind === "device" ? "Same phone" : l.kind}</span>
                  <span className="font-mono text-xs text-[var(--muted)]">{l.kind === "device" ? `ID ending ${l.masked.slice(-4)}` : l.masked}</span>
                  <span className="ml-auto text-xs">used by {l.accounts.length} accounts</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-4 text-sm text-[var(--muted)] sm:px-6 lg:px-8">The accounts in this ring do not share a phone or ID.</p>
          )}
        </div>
        <div className="border-t border-[var(--line)] lg:border-t-0">
          <h2 className="border-b border-[var(--line)] px-4 py-3 text-sm font-semibold sm:px-6 lg:px-8">What the team did</h2>
          {r.actions.length ? (
            <ul className="divide-y divide-[var(--line)]">
              {r.actions.map((a, i) => (
                <li key={i} className="px-4 py-2.5 text-sm sm:px-6 lg:px-8">
                  <div className="flex items-center gap-2">
                    {a.action === "confirm" ? <Ban className="size-4 text-[var(--critical)]" /> : <CheckCircle2 className="size-4 text-[var(--muted)]" />}
                    <span className="font-medium">{ACT_COPY[a.action]?.label ?? a.action}</span>
                    <span className="text-[var(--muted)]">by {a.actor}</span>
                    <span className="ml-auto text-xs text-[var(--muted)]">{fmtDate(a.at)}</span>
                  </div>
                  <div className="mt-0.5 pl-6 text-xs text-[var(--muted)]">
                    {a.accounts.length} account{a.accounts.length > 1 ? "s" : ""}
                    {a.note ? ` · ${a.note}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-4 text-sm text-[var(--muted)] sm:px-6 lg:px-8">Nothing done yet.</p>
          )}
        </div>
      </div>
      <Section title="Questions to other banks" flush description="Each time TheOne asked another bank where this ring's money went, and what it said.">
        {traces?.length ? (
          <DataTable
            rows={traces}
            rowKey={(t) => `${t.at}-${t.bank_code}-${t.account_no}`}
            pageSize={10}
            columns={[
              { key: "at", header: "Sent", render: (t) => <span className="whitespace-nowrap text-xs">{fmtDate(t.at)}</span> },
              { key: "acct", header: "Account", render: (t) => <span className="text-xs">{accountLine(t.account_no, t.bank_code)}</span> },
              { key: "hop", header: "Step", align: "right", render: (t) => t.hop },
              { key: "in", header: "Money received", align: "right", render: (t) => naira(t.amount_in) },
              { key: "on", header: "Moved on", align: "right", render: (t) => (t.status === "answered" ? `${naira(t.amount_onward)} to ${t.onward} account${t.onward === 1 ? "" : "s"}` : "–") },
              { key: "st", header: "Answer", render: (t) => <Badge tone={t.status === "answered" ? "good" : "critical"}>{t.status === "answered" ? "Answered" : "No answer"}</Badge> },
              { key: "by", header: "By", hideBelow: "md", render: (t) => <span className="text-xs">{t.actor}{t.connector !== "http" ? " · not connected to other banks" : ""}</span> },
            ]}
          />
        ) : (
          <p className="px-4 py-4 text-sm text-[var(--muted)] sm:px-6 lg:px-8">No questions sent yet. Use “Follow it into other banks” on the Money flow tab.</p>
        )}
      </Section>
    </>
  );
}
