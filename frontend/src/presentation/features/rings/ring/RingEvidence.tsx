"use client";

/** Evidence tab: each rule that fired, what it means, and what was seen on each account. */
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/presentation/components/ui";
import { plain, strength } from "../explain";
import type { Finding } from "./copy";

export function RingEvidence({ findings, onSelect }: { findings: Finding[]; onSelect: (accountId: string) => void }) {
  const [openFinding, setOpenFinding] = useState<string | null>(null);
  return (
    <div className="border-b border-[var(--line)] bg-[var(--surface)]">
      <p className="border-b border-[var(--line)] px-4 py-3 text-xs text-[var(--muted)] sm:px-6 lg:px-8">Strongest first. Open a finding to see what it means and what was seen on each account.</p>
      <ul className="divide-y divide-[var(--line)]">
        {findings.map((f) => {
          const p = plain(f.code);
          const sg = strength(f.max);
          const isOpen = openFinding === f.code;
          return (
            <li key={f.code}>
              <button
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[var(--surface-2)] sm:px-6 lg:px-8"
                onClick={() => setOpenFinding(isOpen ? null : f.code)}
                aria-expanded={isOpen}
              >
                <ChevronRight className={`size-4 shrink-0 text-[var(--muted)] transition-transform ${isOpen ? "rotate-90" : ""}`} />
                <span className="min-w-0 flex-1 text-sm font-medium">{p.title}</span>
                <span className="hidden text-xs text-[var(--muted)] sm:inline">{f.hits.length} account{f.hits.length > 1 ? "s" : ""}</span>
                <Badge tone={sg.tone}>{sg.label.replace(" evidence", "")}</Badge>
              </button>
              {isOpen && (
                <div className="grid gap-3 bg-[var(--surface-2)] px-4 pb-4 pl-11 sm:px-6 sm:pl-[52px] lg:px-8 lg:pl-[60px]">
                  {p.means && <p className="text-sm text-[var(--ink-2)]">{p.means}</p>}
                  <ul className="grid gap-1">
                    {f.hits.map((h) => (
                      <li key={h.node.id}>
                        <button className="w-full rounded-[4px] bg-[var(--surface)] px-3 py-2 text-left text-sm hover:bg-[var(--brand-soft)]" onClick={() => onSelect(h.node.id)}>
                          <span className="font-medium">{h.node.name || h.node.account_no}</span>
                          <span className="text-[var(--muted)]"> · {h.reason}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
