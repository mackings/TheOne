/** Page structure: header, sections, KPI strips and label/value lists. */
import { ChevronRight, type LucideIcon } from "lucide-react";
import { TONE, type Tone } from "./Badge";
import { cx } from "@/presentation/cx";

export function PageHeader({
  title,
  subtitle,
  actions,
  crumbs,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  crumbs?: { label: string; href?: string }[];
}) {
  return (
    <header className="border-b border-[var(--line)] bg-[var(--surface)] px-4 py-6 sm:px-6 lg:px-8">
      {crumbs && (
        <nav className="mb-1 flex flex-wrap items-center gap-1 text-xs text-[var(--muted)]" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={c.label} className="inline-flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3" />}
              {c.href ? (
                <a href={c.href} className="hover:text-[var(--ink)]">
                  {c.label}
                </a>
              ) : (
                c.label
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
          {subtitle && <div className="mt-1.5 max-w-2xl text-sm text-[var(--muted)]">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** Flat, full-width section. Sections stack edge to edge, divided by hairlines. */
export function Section({
  title,
  description,
  actions,
  children,
  flush,
  className,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return (
    <section className={cx("border-b border-[var(--line)] bg-[var(--surface)]", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-4 sm:px-6 lg:px-8">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-[var(--muted)]">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={flush ? "" : "px-4 py-6 sm:px-6 lg:px-8"}>{children}</div>
    </section>
  );
}

/** A row of KPI tiles separated by hairlines, spanning the full width. */
export function KpiStrip({ children, cols = 4 }: { children: React.ReactNode; cols?: 2 | 3 | 4 | 5 | 6 }) {
  const grid = { 2: "sm:grid-cols-2", 3: "sm:grid-cols-3", 4: "sm:grid-cols-2 xl:grid-cols-4", 5: "sm:grid-cols-3 xl:grid-cols-5", 6: "sm:grid-cols-3 xl:grid-cols-6" }[cols];
  return <div className={cx("grid grid-cols-2 overflow-hidden border-b border-[var(--line)] bg-[var(--surface)]", grid)}>{children}</div>;
}

export function Kpi({ label, value, sub, icon: Icon, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: LucideIcon; tone?: Tone }) {
  return (
    <div className="min-w-0 bg-[var(--surface)] px-4 py-5 shadow-[1px_1px_0_0_var(--line)] sm:px-6">
      <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
        {Icon && <Icon className="size-4" style={{ color: tone ? TONE[tone].dot : "var(--muted)" }} />}
        {label}
      </div>
      <div className="mt-1.5 truncate text-xl font-semibold tabular-nums tracking-tight sm:text-2xl">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

export function DetailList({ items, page }: { items: { label: string; value: React.ReactNode }[]; page?: boolean }) {
  return (
    <dl className="divide-y divide-[var(--line)]">
      {items.map((it) => (
        <div
          key={it.label}
          className={cx(
            "grid gap-3 text-sm",
            page ? "grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-[240px_1fr] sm:gap-3 sm:px-6 lg:px-8" : "grid-cols-[140px_1fr] px-5 py-2.5",
          )}
        >
          <dt className="text-[var(--muted)]">{it.label}</dt>
          <dd className="min-w-0 break-words">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
