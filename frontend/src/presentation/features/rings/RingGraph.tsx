"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { riskLevel } from "@/presentation/components/ui";

import { naira } from "@/presentation/format";
import { ROLE } from "./ring/copy";
import type { RingDetail, RingNode } from "@/domain/network";

const ALL_COLUMNS: { role: RingNode["role"][]; label: string; hint: string; unit: string }[] = [
  { role: ["victim", "source"], label: "Paid in by", hint: "possible victims", unit: "sender" },
  { role: ["collector"], label: "First to receive", hint: "the victims' money", unit: "account" },
  { role: ["layer"], label: "Pass it on", hint: "to hide its source", unit: "account" },
  { role: ["cash_out"], label: "Take it out", hint: "as cash or elsewhere", unit: "account" },
  { role: ["exit"], label: "Other banks", hint: "left our bank", unit: "account" },
  { role: ["traced"], label: "Further on", hint: "where it went next", unit: "account" },
  { role: ["cash_point"], label: "Cash points", hint: "ATMs and POS agents", unit: "cash point" },
];

// Layout in pixels. Rows stretch up to MAX_ROW_H on tall screens; a column is never narrower than
// its heading ("2 accounts · ₦8.2m") and the last one keeps room for its labels.
const ROW_H = 46;
const MAX_ROW_H = 120;
const TOP = 74;
const PAD_L = 24;
const LABEL_W = 210;
const MIN_W = 860;
const COL_MIN = 185;

const LEGEND = [
  { color: "var(--info)", label: "Person who paid in (possible victim)", small: true },
  { color: "var(--critical)", label: "Very high risk" },
  { color: "var(--serious)", label: "High risk" },
  { color: "var(--warning)", label: "Medium risk" },
  { color: "var(--muted)", label: "ATM, POS agent or outside account", small: true },
];

function nodeColor(n: RingNode): string {
  if (n.role === "victim" || n.role === "source") return "var(--info)";
  if (n.role === "cash_point" || n.role === "exit") return "var(--muted)";
  if (n.status === "confirmed_mule") return "var(--critical)";
  return n.risk >= 0.85 ? "var(--critical)" : n.risk >= 0.6 ? "var(--serious)" : "var(--warning)";
}

const compact = (kobo: number) => {
  const n = kobo / 100;
  if (n >= 1e9) return `₦${(n / 1e9).toFixed(1)}bn`;
  if (n >= 1e6) return `₦${(n / 1e6).toFixed(1)}m`;
  if (n >= 1e3) return `₦${Math.round(n / 1e3)}k`;
  return `₦${Math.round(n)}`;
};

/** Every account the selected one got money from (upstream) or passed it on to (downstream), and the
 * payments between them, so the whole trail through the selected account can be highlighted. */
function trailOf(edges: { src: string; dst: string }[], start: string | null) {
  const nodes = new Set<string>();
  const links = new Set<string>();
  if (!start) return { nodes, links };
  nodes.add(start);
  for (const [from, to] of [["src", "dst"], ["dst", "src"]] as const) {
    const seen = new Set([start]);
    const queue = [start];
    while (queue.length) {
      const at = queue.shift()!;
      for (const e of edges)
        if (e[from] === at) {
          links.add(`${e.src}-${e.dst}`);
          if (!seen.has(e[to])) {
            seen.add(e[to]);
            nodes.add(e[to]);
            queue.push(e[to]);
          }
        }
    }
  }
  return { nodes, links };
}

/** Layered money-flow view: who paid in, how it was split and layered, where it left. Fills the available width.
 * `zoom` scales the whole drawing; `fill` makes it take the full height of its parent and lets people drag to move around. */
export function RingGraph({
  ring,
  selected,
  onSelect,
  zoom = 1,
  fill = false,
  onLayout,
}: {
  ring: RingDetail;
  selected: string | null;
  onSelect: (id: string | null) => void;
  zoom?: number;
  fill?: boolean;
  /** Reports the drawing's natural size (its height, and the narrowest width that keeps every column
   * readable), so a full-screen view can size it to fit. */
  onLayout?: (size: { height: number; minWidth: number }) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
  const [width, setWidth] = useState(1100);
  const [boxH, setBoxH] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      setWidth(Math.max(MIN_W, Math.floor(e.contentRect.width)));
      setBoxH(Math.floor(e.contentRect.height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Collapse long tails (many POS agents, many small victims) into one "+N more" node per column.
  const view = useMemo(() => collapse(ring), [ring]);

  const COLUMNS = useMemo(() => ALL_COLUMNS.filter((c) => view.nodes.some((n) => c.role.includes(n.role))), [view]);

  // Zooming lays the map out narrower and scales it up, so it grows to fill the space before it scrolls,
  // but never narrower than each column needs for its heading.
  const minWidth = Math.max(MIN_W, PAD_L + LABEL_W + (COLUMNS.length - 1) * COL_MIN);
  const base = Math.max(minWidth, Math.floor(width / zoom));

  const layout = useMemo(() => {
    const colW = (base - PAD_L - LABEL_W) / Math.max(1, COLUMNS.length - 1);
    const pos = new Map<string, { x: number; y: number; col: number }>();
    const cols = COLUMNS.map((c) =>
      view.nodes
        .filter((n) => c.role.includes(n.role))
        .sort((a, b) => Number(a.id.startsWith("more:")) - Number(b.id.startsWith("more:")) || b.risk - a.risk || a.name.localeCompare(b.name)),
    );
    const rows = Math.max(1, ...cols.map((c) => c.length));
    // Full screen: spread the rows out to fill the height (up to a limit), and centre what is left over.
    const region = fill && boxH ? Math.max(rows * ROW_H, (boxH - 2) / zoom - TOP - 12) : rows * ROW_H;
    const rowH = Math.min(MAX_ROW_H, region / rows);
    const top = TOP + (region - rows * rowH) / 2;
    cols.forEach((list, ci) =>
      list.forEach((n, ri) => {
        const offset = ((rows - list.length) * rowH) / 2;
        pos.set(n.id, { x: PAD_L + 12 + ci * colW, y: top + offset + ri * rowH + rowH / 2, col: ci });
      }),
    );
    // Money arriving at each stage from an earlier stage (the first stage shows what it sent).
    const colOf = (id: string) => pos.get(id)?.col ?? -1;
    const totals = COLUMNS.map((_, ci) =>
      view.edges.reduce((sum, e) => {
        const a = colOf(e.src);
        const b = colOf(e.dst);
        if (ci === 0) return a === 0 && b > 0 ? sum + e.amount : sum;
        return b === ci && a < ci ? sum + e.amount : sum;
      }, 0),
    );
    const counts = cols.map((list) => list.reduce((n, x) => n + (x.id.startsWith("more:") ? Number(x.name.match(/\d+/)?.[0] ?? 0) : 1), 0));
    const maxAmt = Math.max(1, ...view.edges.map((e) => e.amount));
    const chars = Math.max(14, Math.floor((colW - 40) / 6.6));
    const lastChars = Math.floor((LABEL_W - 36) / 6.8);
    return { pos, colW, height: TOP + region + 12, natural: TOP + rows * ROW_H + 12, maxAmt, totals, counts, chars, lastChars };
  }, [view, base, COLUMNS, fill, boxH, zoom]);

  useEffect(() => onLayout?.({ height: layout.natural, minWidth }), [layout.natural, minWidth, onLayout]);

  const trail = useMemo(() => trailOf(view.edges, selected), [view, selected]);

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (!fill || !box.current || e.button !== 0) return;
    drag.current = { x: e.clientX, y: e.clientY, left: box.current.scrollLeft, top: box.current.scrollTop, moved: false };
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || !box.current) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 5) return;
    d.moved = true;
    box.current.scrollLeft = d.left - dx;
    box.current.scrollTop = d.top - dy;
  }
  // A drag should not count as a click on whatever is under the pointer when it ends.
  const wasDrag = () => {
    const moved = drag.current?.moved ?? false;
    drag.current = null;
    return moved;
  };

  const sharedWith = useMemo(() => {
    const s = new Set<string>();
    if (!selected) return s;
    for (const l of ring.identifier_links) if (l.accounts.includes(selected)) l.accounts.forEach((a) => s.add(a));
    return s;
  }, [ring, selected]);

  const cut = (t: string, col = 0) => {
    const max = col === COLUMNS.length - 1 ? layout.lastChars : layout.chars;
    return t.length > max ? t.slice(0, max - 1) + "…" : t;
  };

  return (
    <div className={fill ? "flex h-full min-h-0 flex-col" : undefined}>
      <div
        ref={box}
        className={fill ? "min-h-0 flex-1 cursor-grab overflow-auto active:cursor-grabbing" : "overflow-x-auto"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerLeave={() => (drag.current = null)}
      >
        <svg
          width={base * zoom}
          height={layout.height * zoom}
          viewBox={`0 0 ${base} ${layout.height}`}
          role="img"
          aria-label="Money flow through the ring"
          className="block select-none"
          onClick={(e) => {
            if (wasDrag()) return;
            if (e.target === e.currentTarget) onSelect(null);
          }}
        >
          {COLUMNS.map((c, i) => {
            const x = PAD_L + i * layout.colW;
            return (
              <g key={c.label}>
                {i > 0 && <rect x={x - 12} y={6} width={1} height={layout.height - 12} fill="var(--line)" />}
                <text x={x} y={20} fontSize={12} fill="var(--muted)" fontWeight={600}>
                  {c.label}
                </text>
                <text x={x} y={38} fontSize={13} fill="var(--ink)" fontWeight={600}>
                  {layout.counts[i] ? `${layout.counts[i]} ${c.unit}${layout.counts[i] > 1 ? "s" : ""}` : "None"}
                  {layout.totals[i] ? ` · ${compact(layout.totals[i])}` : ""}
                </text>
                <text x={x} y={54} fontSize={11} fill="var(--muted)">
                  {c.hint}
                </text>
              </g>
            );
          })}
          {view.edges.map((e) => {
            const a = layout.pos.get(e.src);
            const b = layout.pos.get(e.dst);
            if (!a || !b) return null;
            const w = 1.5 + 7 * Math.sqrt(e.amount / layout.maxAmt);
            const hot = trail.links.has(`${e.src}-${e.dst}`);
            const same = a.col === b.col;
            const d = same
              ? `M ${a.x + 10} ${a.y} C ${a.x + 70} ${a.y}, ${b.x + 70} ${b.y}, ${b.x + 10} ${b.y}`
              : `M ${a.x + 10} ${a.y} C ${(a.x + b.x) / 2} ${a.y}, ${(a.x + b.x) / 2} ${b.y}, ${b.x - 10} ${b.y}`;
            return (
              <path
                key={`${e.src}-${e.dst}`}
                d={d}
                fill="none"
                stroke={hot ? "var(--brand)" : "var(--line-strong)"}
                strokeOpacity={selected && !hot ? 0.2 : 0.85}
                strokeWidth={w}
                strokeLinecap="round"
              >
                <title>{`${naira(e.amount)} in ${e.count} transfer${e.count > 1 ? "s" : ""} · ${e.channels.join(", ")}`}</title>
              </path>
            );
          })}
          {view.nodes.map((n) => {
            const p = layout.pos.get(n.id);
            if (!p) return null;
            const more = n.id.startsWith("more:");
            const isSel = n.id === selected;
            const shared = sharedWith.has(n.id) && !isSel;
            const outer = n.role === "victim" || n.role === "cash_point" || n.role === "exit" || n.role === "source";
            const r = outer ? 7 : n.role === "traced" ? 7 + n.risk * 5 : 10 + n.risk * 5;
            return (
              <g
                key={n.id}
                onClick={(ev) => {
                  ev.stopPropagation();
                  if (!wasDrag() && !more) onSelect(n.id);
                }}
                style={{ cursor: more ? "default" : "pointer" }}
                opacity={selected && !trail.nodes.has(n.id) && !shared ? 0.35 : 1}
              >
                <circle cx={p.x} cy={p.y} r={r + 8} fill="transparent" />
                {(isSel || shared) && (
                  <circle cx={p.x} cy={p.y} r={r + 4} fill="none" stroke="var(--ink)" strokeWidth={isSel ? 2 : 1.5} strokeDasharray={shared ? "3 3" : undefined} />
                )}
                <circle cx={p.x} cy={p.y} r={r} fill={nodeColor(n)} stroke="var(--surface)" strokeWidth={2} />
                <text x={p.x + r + 8} y={more ? p.y - 3 : p.y + 4} fontSize={12.5} fill="var(--ink)" fontWeight={outer ? 400 : 600}
                  stroke="var(--surface)" strokeWidth={4} strokeLinejoin="round" paintOrder="stroke">
                  {cut(n.name || "Unknown", p.col)}
                </text>
                {more && (
                  <text x={p.x + r + 8} y={p.y + 12} fontSize={11} fill="var(--muted)">
                    {n.account_no}
                  </text>
                )}
                {!more && <title>{`${n.name || "Unknown"}\nAccount ${n.account_no} · bank ${n.bank_code}\n${ROLE[n.role] ?? n.role}${outer ? "" : ` · ${riskLevel(n.risk).label} risk`}`}</title>}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-4 flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--line)] pt-3 text-xs text-[var(--ink-2)]">
        {LEGEND.map((l) => (
          <span key={l.label} className="inline-flex items-center gap-2">
            <span className="rounded-full" style={{ background: l.color, width: l.small ? 10 : 14, height: l.small ? 10 : 14 }} />
            {l.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-2">
          <svg width="28" height="10" aria-hidden><path d="M2 5 H26" stroke="var(--line-strong)" strokeWidth="6" strokeLinecap="round" /></svg>
          Thicker line, more money
        </span>
        <span className="inline-flex items-center gap-2">
          <svg width="16" height="16" aria-hidden><circle cx="8" cy="8" r="6.5" fill="none" stroke="var(--ink)" strokeDasharray="3 3" /></svg>
          Uses the same phone or ID as the selected account
        </span>
      </div>
    </div>
  );
}

const KEEP = 7;

function collapse(ring: RingDetail): { nodes: RingNode[]; edges: RingDetail["edges"] } {
  const inflow = new Map<string, number>();
  for (const e of ring.edges) {
    inflow.set(e.dst, (inflow.get(e.dst) ?? 0) + e.amount);
    inflow.set(e.src, (inflow.get(e.src) ?? 0) + e.amount);
  }
  const merged = new Map<string, string>();
  const extra: RingNode[] = [];
  const tail: Record<string, string> = { cash_point: "cash points", exit: "accounts at other banks", traced: "traced accounts", victim: "senders" };
  for (const group of [["cash_point"], ["exit"], ["traced"], ["victim", "source"]] as RingNode["role"][][]) {
    const list = ring.nodes.filter((n) => group.includes(n.role)).sort((a, b) => (inflow.get(b.id) ?? 0) - (inflow.get(a.id) ?? 0));
    if (list.length <= KEEP + 1) continue;
    const rest = list.slice(KEEP);
    const id = `more:${group[0]}`;
    rest.forEach((n) => merged.set(n.id, id));
    extra.push({
      id, name: `+${rest.length} more`, bank_code: "", account_no: tail[group[0]],
      home: true, role: group[0], risk: 0, status: "active", signals: [],
    });
  }
  if (!merged.size) return { nodes: ring.nodes, edges: ring.edges };
  const edges = new Map<string, RingDetail["edges"][number]>();
  for (const e of ring.edges) {
    const src = merged.get(e.src) ?? e.src;
    const dst = merged.get(e.dst) ?? e.dst;
    const k = `${src}>${dst}`;
    const cur = edges.get(k);
    if (cur) {
      cur.amount += e.amount;
      cur.count += e.count;
      cur.channels = Array.from(new Set([...cur.channels, ...e.channels]));
    } else edges.set(k, { ...e, src, dst, channels: [...e.channels] });
  }
  return { nodes: [...ring.nodes.filter((n) => !merged.has(n.id)), ...extra], edges: [...edges.values()] };
}
