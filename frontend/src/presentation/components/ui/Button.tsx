import { Loader2, type LucideIcon } from "lucide-react";
import { cx } from "@/presentation/cx";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  loading,
  className,
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; icon?: LucideIcon; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: "bg-[var(--brand)] text-white hover:bg-[var(--brand-strong)] border-transparent",
    secondary: "bg-[var(--surface)] text-[var(--ink)] border-[var(--line-strong)] hover:bg-[var(--surface-2)]",
    ghost: "bg-transparent text-[var(--ink-2)] border-transparent hover:bg-[var(--surface-2)]",
    danger: "bg-[var(--critical)] text-white hover:opacity-90 border-transparent",
  };
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[6px] border font-medium transition-colors disabled:cursor-not-allowed disabled:border-[var(--line)] disabled:bg-[var(--surface-2)] disabled:text-[var(--muted)]",
        size === "sm" ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-sm",
        styles[variant],
        className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : Icon ? <Icon className="size-4" /> : null}
      {children}
    </button>
  );
}
