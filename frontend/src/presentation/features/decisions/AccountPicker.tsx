"use client";

/** Search for an account by name or number and pick one. */
import { useEffect, useState } from "react";
import { Field, Input, inputCls, RiskScore } from "@/presentation/components/ui";
import { accountLine } from "@/presentation/format";
import type { AccountBrief } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

export function AccountPicker({ label, value, onChange }: { label: string; value: AccountBrief | null; onChange: (a: AccountBrief | null) => void }) {
  const net = useNetwork();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<AccountBrief[]>([]);
  const searching = q.trim().length >= 2;
  useEffect(() => {
    if (!searching) return;
    const t = setTimeout(() => net.search(q).then(setHits).catch(() => setHits([])), 200);
    return () => clearTimeout(t);
  }, [net, q, searching]);
  return (
    <Field label={label}>
      {value ? (
        <div className={`${inputCls} flex w-full items-center justify-between`}>
          <span className="truncate">{value.name} <span className="text-[var(--muted)]">· {accountLine(value.account_no, value.bank_code, value.home)}</span></span>
          <button className="text-xs font-medium text-[var(--brand)]" onClick={() => onChange(null)}>Change</button>
        </div>
      ) : (
        <div className="relative">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or account number" />
          {searching && hits.length > 0 && (
            <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-[6px] border border-[var(--line)] bg-[var(--surface)] shadow-lg">
              {hits.map((h) => (
                <li key={h.id}>
                  <button className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-[var(--surface-2)]" onClick={() => { onChange(h); setQ(""); setHits([]); }}>
                    <span className="truncate">{h.name} <span className="text-[var(--muted)]">· {accountLine(h.account_no, h.bank_code, h.home)}</span></span>
                    <RiskScore value={h.risk} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Field>
  );
}
