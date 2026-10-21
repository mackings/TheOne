"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "./Button";
import { EmptyState } from "./Feedback";
import { cx } from "@/presentation/cx";

export type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  sort?: (row: T) => number | string;
  align?: "left" | "right";
  hideBelow?: "sm" | "md" | "lg" | "xl" | "2xl";
  width?: string;
};

const HIDE = { sm: "hidden sm:table-cell", md: "hidden md:table-cell", lg: "hidden lg:table-cell", xl: "hidden xl:table-cell", "2xl": "hidden 2xl:table-cell" };

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  loading,
  empty,
  pageSize = 15,
  initialSort,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (r: T) => string;
  onRowClick?: (r: T) => void;
  selectedKey?: string | null;
  loading?: boolean;
  empty?: React.ReactNode;
  pageSize?: number;
  initialSort?: { key: string; dir: "asc" | "desc" };
}) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [page, setPage] = useState(0);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    const s = [...rows].sort((a, b) => {
      const x = col.sort!(a);
      const y = col.sort!(b);
      return x < y ? -1 : x > y ? 1 : 0;
    });
    return sort.dir === "desc" ? s.reverse() : s;
  }, [rows, sort, columns]);
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, pages - 1);
  const view = sorted.slice(current * pageSize, current * pageSize + pageSize);

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-[var(--line)] bg-[var(--surface-2)] text-left">
              {columns.map((c, i) => (
                <th
                  key={c.key}
                  scope="col"
                  style={{ width: c.width }}
                  className={cx(
                    "whitespace-nowrap px-3 py-2.5 text-[13px] font-medium text-[var(--muted)]",
                    i === 0 && "pl-4 sm:pl-6 lg:pl-8",
                    i === columns.length - 1 && "pr-4 sm:pr-6 lg:pr-8",
                    c.align === "right" && "text-right",
                    c.hideBelow && HIDE[c.hideBelow],
                  )}
                >
                  {c.sort ? (
                    <button
                      className={cx("inline-flex items-center gap-1 hover:text-[var(--ink)]", c.align === "right" && "flex-row-reverse")}
                      onClick={() => {
                        setPage(0);
                        setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === "asc" ? "desc" : "asc" } : { key: c.key, dir: "desc" }));
                      }}
                    >
                      {c.header}
                      {sort?.key === c.key ? sort.dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-40" />}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !rows.length
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-b border-[var(--line)]">
                    {columns.map((c, j) => (
                      <td key={c.key} className={cx("px-3 py-3.5", j === 0 && "pl-4 sm:pl-6 lg:pl-8", c.hideBelow && HIDE[c.hideBelow])}>
                        <div className="skeleton h-3.5 rounded" style={{ width: `${50 + ((i * 7 + j * 13) % 40)}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              : view.map((r) => {
                  const k = rowKey(r);
                  return (
                    <tr
                      key={k}
                      onClick={onRowClick ? () => onRowClick(r) : undefined}
                      className={cx(
                        "border-b border-[var(--line)] transition-colors",
                        onRowClick && "cursor-pointer hover:bg-[var(--surface-2)]",
                        selectedKey === k && "bg-[var(--brand-soft)] hover:bg-[var(--brand-soft)]",
                      )}
                    >
                      {columns.map((c, i) => (
                        <td
                          key={c.key}
                          className={cx(
                            "px-3 py-3 align-middle",
                            i === 0 && "pl-4 sm:pl-6 lg:pl-8",
                            i === columns.length - 1 && "pr-4 sm:pr-6 lg:pr-8",
                            c.align === "right" && "text-right tabular-nums",
                            c.hideBelow && HIDE[c.hideBelow],
                          )}
                        >
                          {c.render(r)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>
      {!loading && !rows.length && (empty ?? <EmptyState title="Nothing to show" description="No records match these filters." />)}
      {rows.length > pageSize && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 text-xs text-[var(--muted)] sm:px-6 lg:px-8">
          <span className="tabular-nums">
            {current * pageSize + 1}–{Math.min(sorted.length, (current + 1) * pageSize)} of {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" icon={ChevronLeft} disabled={current === 0} onClick={() => setPage(current - 1)} aria-label="Previous page" />
            <span className="px-2 tabular-nums">
              Page {current + 1} of {pages}
            </span>
            <Button size="sm" variant="ghost" icon={ChevronRight} disabled={current >= pages - 1} onClick={() => setPage(current + 1)} aria-label="Next page" />
          </div>
        </div>
      )}
    </div>
  );
}
