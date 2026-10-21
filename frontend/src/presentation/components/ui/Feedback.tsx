"use client";

/** Empty and error states. */
import { Info, type LucideIcon, XCircle } from "lucide-react";
import { Button } from "./Button";

export function EmptyState({ icon: Icon = Info, title, description, action }: { icon?: LucideIcon; title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="rounded-full bg-[var(--surface-2)] p-3">
        <Icon className="size-6 text-[var(--muted)]" />
      </div>
      <div className="text-sm font-semibold">{title}</div>
      {description && <p className="max-w-md text-sm text-[var(--muted)]">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function InlineError({ error, onRetry }: { error?: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-3 border-b border-[var(--line)] bg-[var(--critical-soft)] px-4 py-3 text-sm sm:px-6 lg:px-8" role="alert">
      <XCircle className="mt-0.5 size-4 shrink-0 text-[var(--critical)]" />
      <div className="flex-1">{error}</div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
