"use client";

/** Accounts tab: the ring's members, with watchlist and release per account. */
import { Badge, Button, DataTable, RiskScore } from "@/presentation/components/ui";

import { accountLine } from "@/presentation/format";
import { ACCOUNT_STATUS, pick } from "@/presentation/status";
import { plain, ROLE_PLAIN } from "../explain";
import { type Act, ROLE } from "./copy";
import type { RingNode } from "@/domain/network";

export function RingAccounts({ members, selected, onSelect, onAct }: {
  members: RingNode[];
  selected: string | null;
  onSelect: (accountId: string) => void;
  onAct: (a: Act) => void;
}) {
  return (
    <div className="border-b border-[var(--line)] bg-[var(--surface)]">
      <DataTable<RingNode>
        rows={members}
        rowKey={(n) => n.id}
        onRowClick={(n) => onSelect(n.id)}
        selectedKey={selected}
        initialSort={{ key: "risk", dir: "desc" }}
        pageSize={20}
        columns={[
          { key: "name", header: "Account", sort: (n) => n.name, render: (n) => <div><div className="font-medium">{n.name || "Unknown"}</div><div className="text-xs text-[var(--muted)]">{accountLine(n.account_no, n.bank_code, n.home)}</div></div> },
          { key: "role", header: "Part in the ring", sort: (n) => n.role, render: (n) => <span title={ROLE_PLAIN[n.role]?.means}>{ROLE[n.role] ?? n.role}</span> },
          { key: "risk", header: "Risk", sort: (n) => n.risk, render: (n) => <RiskScore value={n.risk} /> },
          { key: "why", header: "Main warning sign", hideBelow: "lg", render: (n) => <span className="text-xs text-[var(--ink-2)]">{n.signals[0] ? plain(n.signals[0].code).title : "–"}</span> },
          { key: "status", header: "Status", sort: (n) => n.status, render: (n) => { const s = pick(ACCOUNT_STATUS, n.status); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; } },
          {
            key: "act",
            header: "",
            align: "right",
            render: (n) =>
              n.status === "watchlist" ? (
                <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); onAct({ action: "release", accounts: [n.id] }); }}>Stop watching</Button>
              ) : n.status !== "confirmed_mule" ? (
                <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); onAct({ action: "watchlist_24h", accounts: [n.id] }); }}>Watch 24 h</Button>
              ) : null,
          },
        ]}
      />
    </div>
  );
}
