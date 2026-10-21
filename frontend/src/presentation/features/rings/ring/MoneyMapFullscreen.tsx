"use client";

/** The money map, full screen: bigger, zoomable and draggable, with the selected account's whole money trail lit up. */
import { AudioLines, Minimize2, Minus, Plus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/presentation/components/ui";

import { ringName } from "@/presentation/format";
import { RingGraph } from "../RingGraph";
import { ROLE } from "./copy";
import type { RingDetail } from "@/domain/network";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const STEP = 0.25;
const clamp = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(z * 100) / 100));
// Height of the colour key under the map.
const LEGEND_H = 64;

export function MoneyMapFullscreen({ ring, selected, onSelect, onDetails, onBriefing, onClose }: {
  ring: RingDetail;
  selected: string | null;
  onSelect: (id: string | null) => void;
  /** Open the account panel for the selected account. */
  onDetails: () => void;
  /** Ask Ziva to explain this ring. */
  onBriefing?: () => void;
  onClose: () => void;
}) {
  // Null until the map is sized to fit the screen.
  const [zoom, setZoom] = useState<number | null>(null);
  const [fit, setFit] = useState(1);
  const body = useRef<HTMLDivElement>(null);
  const node = ring.nodes.find((n) => n.id === selected) ?? null;
  const z = zoom ?? fit;

  // Fit the whole map on screen: as large as the height allows, and a little smaller on narrow screens
  // so every column shows. On a phone it stays full size and you drag across.
  const natural = useRef<{ height: number; minWidth: number } | null>(null);
  const refit = useCallback(() => {
    const el = body.current;
    const n = natural.current;
    if (!el || !n) return;
    const roomH = el.clientHeight - LEGEND_H - 20;
    const roomW = el.clientWidth - 48;
    if (roomH <= 0 || roomW <= 0) return;
    const tall = Math.min(2, Math.max(1, roomH / n.height));
    const wide = roomW / n.minWidth;
    // Shrinking more than a quarter makes names too small to read: keep full size and drag across instead.
    const f = wide >= tall ? tall : wide >= 0.75 ? wide : 1;
    setFit(Math.floor(f * 100) / 100);
  }, []);
  const onLayout = useCallback((size: { height: number; minWidth: number }) => {
    natural.current = size;
    refit();
  }, [refit]);
  useEffect(() => {
    const el = body.current;
    if (!el) return;
    const ro = new ResizeObserver(refit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [refit]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "+" || e.key === "=") setZoom((v) => clamp((v ?? fit) + STEP));
      else if (e.key === "-") setZoom((v) => clamp((v ?? fit) - STEP));
      else if (e.key === "0") setZoom(null);
    };
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Hides the floating "Ask TheOne" button.
    document.body.dataset.fullscreen = "true";
    return () => {
      document.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      delete document.body.dataset.fullscreen;
    };
  }, [onClose, fit]);

  // Rendered on <body> so the page layout around it (padding, scrolling) cannot affect it.
  return createPortal(
    <div className="fixed inset-0 z-[35] flex flex-col bg-[var(--surface)]" role="dialog" aria-modal="true" aria-label={`Money flow, ${ringName(ring)}`}>
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--line)] px-4 py-3 sm:px-6">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold">Money flow · {ringName(ring)}</h2>
          <p className="hidden text-xs text-[var(--muted)] sm:block">Click an account to follow its money. Drag to move around, + and − to zoom, Esc to close.</p>
        </div>
        <div className="flex items-center rounded-[6px] border border-[var(--line-strong)]" role="group" aria-label="Zoom">
          <button className="flex size-9 items-center justify-center text-[var(--ink-2)] hover:bg-[var(--surface-2)] disabled:opacity-40" aria-label="Zoom out"
            disabled={z <= MIN_ZOOM} onClick={() => setZoom(clamp(z - STEP))}>
            <Minus className="size-4" />
          </button>
          <button className="h-9 min-w-16 border-x border-[var(--line-strong)] px-2 text-sm tabular-nums hover:bg-[var(--surface-2)]" title="Fit to screen" onClick={() => setZoom(null)}>
            {zoom == null ? "Fit" : `${Math.round(z * 100)}%`}
          </button>
          <button className="flex size-9 items-center justify-center text-[var(--ink-2)] hover:bg-[var(--surface-2)] disabled:opacity-40" aria-label="Zoom in"
            disabled={z >= MAX_ZOOM} onClick={() => setZoom(clamp(z + STEP))}>
            <Plus className="size-4" />
          </button>
        </div>
        {onBriefing && <Button icon={AudioLines} onClick={onBriefing}>Talk me through it</Button>}
        <Button icon={Minimize2} onClick={onClose}>Close</Button>
      </div>

      {node && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-[var(--line)] bg-[var(--brand-soft)] px-4 py-2.5 text-sm sm:px-6">
          <span>
            Following <span className="font-semibold">{node.name || node.account_no}</span>
            <span className="text-[var(--muted)]"> · {ROLE[node.role] ?? node.role}</span>
          </span>
          <span className="text-xs text-[var(--muted)]">Lit up: where its money came from and everywhere it went next.</span>
          <span className="ml-auto flex gap-2">
            {ring.summary.roles[node.id] && <Button size="sm" onClick={onDetails}>Why it was flagged</Button>}
            <Button size="sm" variant="ghost" icon={X} onClick={() => onSelect(null)}>Clear</Button>
          </span>
        </div>
      )}

      <div ref={body} className="min-h-0 flex-1 px-4 pb-4 pt-3 sm:px-6">
        <RingGraph ring={ring} selected={selected} onSelect={onSelect} zoom={z} fill onLayout={onLayout} />
      </div>
    </div>,
    document.body,
  );
}
