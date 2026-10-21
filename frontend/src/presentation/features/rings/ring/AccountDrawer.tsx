"use client";

/** Side panel for one account on the money map: its role, risk and why it was flagged. */
import { Clock } from "lucide-react";
import { Badge, Button, DetailList, Drawer, RiskScore } from "@/presentation/components/ui";

import { accountLine, bankName } from "@/presentation/format";
import { ACCOUNT_STATUS, pick } from "@/presentation/status";
import { plain, ROLE_PLAIN, strength } from "../explain";
import { type Act, ROLE } from "./copy";
import type { RingNode } from "@/domain/network";

export function AccountDrawer({ node, member, onClose, onAct }: {
  node: RingNode | null;
  /** The account is in the ring (not a victim, cash point or other bank). */
  member: boolean;
  onClose: () => void;
  onAct: (a: Act) => void;
}) {
  return (
    <Drawer
      open={!!node}
      onClose={onClose}
      title={node?.name || "Account"}
      subtitle={node ? `${accountLine(node.account_no, node.bank_code, node.home)} · ${ROLE[node.role] ?? node.role}` : undefined}
      footer={
        node && member ? (
          node.status === "watchlist" ? (
            <Button onClick={() => onAct({ action: "release", accounts: [node.id] })}>Stop watching</Button>
          ) : (
            <Button variant="primary" icon={Clock} onClick={() => onAct({ action: "watchlist_24h", accounts: [node.id] })}>
              Watch for 24 hours
            </Button>
          )
        ) : undefined
      }
    >
      {node && (
        <>
          <DetailList
            items={[
              { label: "Part in the ring", value: ROLE[node.role] ?? node.role },
              { label: "Bank", value: node.home ? "Our customer" : bankName(node.bank_code) },
              ...(member
                ? [
                    { label: "Risk", value: <RiskScore value={node.risk} /> },
                    { label: "Status", value: (() => { const s = pick(ACCOUNT_STATUS, node.status); return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>; })() },
                  ]
                : []),
            ]}
          />
          {member ? (
            <div className="border-t border-[var(--line)] px-5 py-4">
              <h3 className="mb-1 text-sm font-semibold text-[var(--ink)]">Why it was flagged</h3>
              <p className="mb-3 text-sm text-[var(--ink-2)]">{ROLE_PLAIN[node.role]?.means}</p>
              <ul className="grid gap-2">
                {node.signals.map((s) => {
                  const sg = strength(s.weight);
                  return (
                    <li key={s.code} className="border-l-2 border-[var(--brand)] bg-[var(--surface-2)] px-3 py-2.5 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium">{plain(s.code).title}</span>
                        <Badge tone={sg.tone}>{sg.label}</Badge>
                      </div>
                      <div className="mt-0.5 text-xs text-[var(--ink-2)]">What we saw: {s.reason}.</div>
                      {plain(s.code).means && <div className="mt-1 text-xs text-[var(--muted)]">{plain(s.code).means}</div>}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <p className="border-t border-[var(--line)] px-5 py-4 text-sm text-[var(--muted)]">
              {node.role === "victim" ? "Paid money into the ring. Treated as a possible victim and never scored for it." : "Where money left the ring: a cash point or an account outside it."}
            </p>
          )}
        </>
      )}
    </Drawer>
  );
}
