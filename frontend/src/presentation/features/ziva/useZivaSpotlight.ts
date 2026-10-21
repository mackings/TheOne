"use client";

/** Light up the account Ziva is talking about, by spotting its name in what she says. */
import { useEffect, useMemo } from "react";

import type { RingNode } from "@/domain/network";
import { useZiva } from "./ZivaProvider";

type Named = { id: string; full: string; surname: string | null };

/** Where a name last appears as whole words, or -1. */
function lastWord(text: string, name: string): number {
  let at = -1;
  for (const m of text.matchAll(new RegExp(`\\b${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g"))) at = m.index;
  return at;
}

/** The account named last: by full name, or by surname when no other account shares it. */
function lastNamed(text: string, names: Named[]): string | null {
  const t = text.toLowerCase();
  let best: { id: string; at: number } | null = null;
  for (const n of names) {
    const at = Math.max(lastWord(t, n.full), n.surname ? lastWord(t, n.surname) : -1);
    if (at >= 0 && (!best || at > best.at)) best = { id: n.id, at };
  }
  return best?.id ?? null;
}

export function useZivaSpotlight(nodes: RingNode[] | undefined, onSpotlight: (nodeId: string | null) => void) {
  const { listen } = useZiva();
  const names = useMemo<Named[]>(() => {
    // ATMs and POS agents have generic names ("ATM Cash") that ordinary speech would match.
    const named = (nodes ?? []).filter((n) => n.name?.trim() && n.role !== "cash_point");
    const surnames = named.map((n) => n.name.trim().split(/\s+/).pop()!.toLowerCase());
    return named.map((n, i) => ({
      id: n.id,
      full: n.name.trim().toLowerCase(),
      surname: surnames.filter((x) => x === surnames[i]).length === 1 && surnames[i].length > 3 ? surnames[i] : null,
    }));
  }, [nodes]);

  useEffect(() => {
    let lit: string | null = null;
    return listen((spoken) => {
      if (!spoken) {
        lit = null;
        onSpotlight(null);
        return;
      }
      const id = lastNamed(spoken, names);
      if (id && id !== lit) {
        lit = id;
        onSpotlight(id);
      }
    });
  }, [listen, names, onSpotlight]);
}
