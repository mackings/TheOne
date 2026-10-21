"use client";

/** Dialogs and drawers, rendered in a portal and closed with Escape. */
import { AlertTriangle, Info, type LucideIcon, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TONE, type Tone } from "./Badge";
import { Button } from "./Button";
import { Field, Input } from "./Form";
import { cx } from "@/presentation/cx";

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
}

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  tone,
  icon: Icon,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
}) {
  useEscape(open, onClose);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) ref.current?.querySelector<HTMLElement>("[data-autofocus], button, input, select")?.focus();
  }, [open]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/40" style={{ animation: "fade-in 120ms ease-out" }} onClick={onClose} />
      <div ref={ref} className="relative w-full max-w-lg border border-[var(--line)] bg-[var(--surface)] shadow-xl sm:rounded-[8px]" style={{ animation: "toast-in 160ms ease-out" }}>
        <div className="flex items-start gap-3 px-5 pb-3 pt-5">
          {Icon && (
            <div className="rounded-full p-2" style={{ background: TONE[tone ?? "neutral"].bg }}>
              <Icon className="size-5" style={{ color: TONE[tone ?? "neutral"].dot }} />
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{title}</h2>
            {description && <div className="mt-1 text-sm text-[var(--muted)]">{description}</div>}
          </div>
          <button className="rounded p-1 text-[var(--muted)] hover:bg-[var(--surface-2)]" onClick={onClose} aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        {children && <div className="px-5 pb-4">{children}</div>}
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--line)] bg-[var(--surface-2)] px-5 py-3 sm:rounded-b-[8px]">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Confirmation for consequential actions. `danger` confirms in red; optional typed confirmation. */
export function ConfirmDialog({
  open,
  onCancel,
  onConfirm,
  title,
  message,
  confirmLabel = "Confirm",
  danger,
  busy,
  requireText,
  children,
}: {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  requireText?: string;
  children?: React.ReactNode;
}) {
  const [typed, setTyped] = useState("");
  const ok = !requireText || typed.trim().toUpperCase() === requireText.toUpperCase();
  return (
    <Dialog
      open={open}
      onClose={() => {
        setTyped("");
        onCancel();
      }}
      title={title}
      description={message}
      icon={danger ? AlertTriangle : Info}
      tone={danger ? "critical" : "info"}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={() => ok && onConfirm()} loading={busy} disabled={!ok}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
      {requireText && (
        <Field label={`Type ${requireText} to confirm`} className="mt-2">
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} data-autofocus />
        </Field>
      )}
    </Dialog>
  );
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  useEscape(open, onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/30" style={{ animation: "fade-in 120ms ease-out" }} onClick={onClose} />
      <aside
        className={cx("relative flex h-full w-full flex-col border-l border-[var(--line)] bg-[var(--surface)] shadow-2xl", wide ? "sm:max-w-2xl" : "sm:max-w-md")}
        style={{ animation: "drawer-in 180ms ease-out" }}
      >
        <div className="flex items-start gap-3 border-b border-[var(--line)] px-5 py-4">
          <div className="min-w-0 flex-1">
            <div className="truncate text-base font-semibold">{title}</div>
            {subtitle && <div className="mt-0.5 text-xs text-[var(--muted)]">{subtitle}</div>}
          </div>
          <button className="rounded p-1 text-[var(--muted)] hover:bg-[var(--surface-2)]" onClick={onClose} aria-label="Close panel">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--line)] bg-[var(--surface-2)] px-5 py-3">{footer}</div>}
      </aside>
    </div>,
    document.body,
  );
}
