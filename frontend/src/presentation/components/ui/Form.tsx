"use client";

/** Form controls, filters and tabs. */
import { type LucideIcon, Search, SlidersHorizontal, X } from "lucide-react";
import { useState } from "react";
import { cx } from "@/presentation/cx";

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cx("grid gap-1 text-sm", className)}>
      <span className="text-xs font-medium text-[var(--ink-2)]">{label}</span>
      {children}
      {hint && <span className="text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}

export const inputCls =
  "h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none transition-colors placeholder:text-[var(--muted)] focus:border-[var(--brand)]";

/** Full width unless the caller sets its own width class. */
const width = (c?: string) => (c && /(^|\s)(sm:|md:|lg:)?w-/.test(c) ? "" : "w-full");

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(inputCls, width(props.className), props.className)} />;
}

export function Select({ options, ...props }: React.SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  return (
    <select {...props} className={cx(inputCls, width(props.className), "pr-8", props.className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function SearchInput({ value, onChange, placeholder = "Search", className }: { value: string; onChange: (v: string) => void; placeholder?: string; className?: string }) {
  return (
    <div className={cx("relative", className)}>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={cx(inputCls, "w-full pl-9")} aria-label={placeholder} />
      {value && (
        <button className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[var(--muted)] hover:text-[var(--ink)]" onClick={() => onChange("")} aria-label="Clear search">
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

/** Segmented control for a small set of mutually exclusive filters, with optional counts. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex max-w-full overflow-x-auto rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] p-0.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] px-3 text-[13px] font-medium transition-colors",
            o.value === value ? "bg-[var(--ink)] text-[var(--surface)]" : "text-[var(--ink-2)] hover:bg-[var(--surface-2)]",
          )}
        >
          {o.label}
          {o.count != null && <span className={cx("rounded px-1 text-[11px] tabular-nums", o.value === value ? "bg-white/20" : "bg-[var(--surface-2)]")}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Filter row: the main controls always show; `more` controls sit behind a "Filters" button.
 * `active` is how many of the hidden filters are set, so the button can say so. */
export function FilterBar({ children, right, more, active = 0 }: { children: React.ReactNode; right?: React.ReactNode; more?: React.ReactNode; active?: number }) {
  const [open, setOpen] = useState(false);
  const shown = open || active > 0;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-4 py-3.5 sm:px-6 lg:px-8">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        {children}
        {more && (
          <button
            type="button"
            onClick={() => setOpen(!shown)}
            aria-expanded={shown}
            className={cx(
              "inline-flex h-10 items-center gap-2 rounded-[6px] border px-3 text-sm font-medium",
              shown ? "border-[var(--ink)] text-[var(--ink)]" : "border-[var(--line-strong)] text-[var(--ink-2)] hover:bg-[var(--surface-2)]",
            )}
          >
            <SlidersHorizontal className="size-4" />
            Filters{active ? ` (${active})` : ""}
          </button>
        )}
      </div>
      {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
      {more && shown && <div className="flex w-full flex-wrap items-center gap-2">{more}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: string; icon?: LucideIcon }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-[var(--line)] bg-[var(--surface)] px-4 sm:px-6 lg:px-8" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={t.value === value}
          onClick={() => onChange(t.value)}
          className={cx(
            "-mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-medium transition-colors",
            t.value === value ? "border-[var(--brand)] text-[var(--ink)]" : "border-transparent text-[var(--muted)] hover:text-[var(--ink)]",
          )}
        >
          {t.icon && <t.icon className="size-4" />}
          {t.label}
        </button>
      ))}
    </div>
  );
}
