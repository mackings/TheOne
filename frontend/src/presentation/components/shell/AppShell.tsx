"use client";

import {
  ArrowLeftRight,
  BellRing,
  Database,
  House,
  LayoutDashboard,
  type LucideIcon,
  Menu,
  Network,
  PlayCircle,
  Settings,
  ShieldCheck,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Badge } from "@/presentation/components/ui";
import { cx } from "@/presentation/cx";

import { ZivaProvider } from "@/presentation/features/ziva/ZivaProvider";
import { ZivaWidget } from "@/presentation/features/ziva/ZivaWidget";
import type { NetSummary } from "@/domain/network";
import { useNetwork } from "@/presentation/hooks/gateways";

type Item = { href: string; label: string; icon: LucideIcon; badge?: "alerts" };
const NAV: { group: string; items: Item[] }[] = [
  {
    group: "",
    items: [
      { href: "/", label: "Home", icon: House },
      { href: "/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/simulation", label: "How it works", icon: PlayCircle },
    ],
  },
  {
    group: "Watch",
    items: [
      { href: "/network/alerts", label: "Alerts", icon: BellRing, badge: "alerts" },
      { href: "/network/decisions", label: "Payments checked", icon: ArrowLeftRight },
    ],
  },
  {
    group: "Investigate",
    items: [
      { href: "/network", label: "Mule rings", icon: Network },
      { href: "/network/accounts", label: "Accounts", icon: Users },
    ],
  },
  { group: "Customers", items: [{ href: "/customers", label: "Customers", icon: UserRound }] },
  {
    group: "Setup",
    items: [
      { href: "/network/ops", label: "Data & bank", icon: Database },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

// Voice and iris pages are opened from a customer, so they keep Customers highlighted.
const CUSTOMER_PAGES = ["/enrol", "/verify", "/iris"];

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  if (href === "/network") return path === "/network" || path.startsWith("/network/rings");
  if (href === "/customers" && CUSTOMER_PAGES.some((p) => path.startsWith(p))) return true;
  return path === href || path.startsWith(href + "/");
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const net = useNetwork();
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<NetSummary | null>(null);
  const [openAlerts, setOpenAlerts] = useState<number | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      net.summary().then((s) => alive && (setSummary(s), setOffline(false))).catch(() => alive && setOffline(true));
      net.alerts().then((a) => alive && setOpenAlerts(a.length)).catch(() => {});
    };
    const first = setTimeout(tick, 0);
    const t = setInterval(tick, 20_000);
    return () => {
      alive = false;
      clearTimeout(first);
      clearInterval(t);
    };
  }, [net]);

  // On desktop the top bar only appears when there is something to warn about.
  const notice = offline || summary?.mode === "shadow" || summary?.bank_connector === "none" || !!openAlerts;

  const nav = (
    <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Main">
      <Suspense fallback={<NavLinks path={null} openAlerts={openAlerts} onNavigate={() => setOpen(false)} />}>
        <CurrentNav openAlerts={openAlerts} onNavigate={() => setOpen(false)} />
      </Suspense>
    </nav>
  );

  const brand = (
    <div className="flex h-14 items-center gap-2.5 border-b border-[var(--sidebar-line)] px-5">
      <div className="flex size-8 items-center justify-center rounded-[6px] bg-[var(--brand)]">
        <ShieldCheck className="size-5 text-white" />
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-semibold text-[var(--sidebar-strong)]">TheOne</div>
        <div className="text-[11px] text-[var(--sidebar-muted)]">Fraud defence console</div>
      </div>
    </div>
  );

  return (
    <ZivaProvider>
      <div className="min-h-screen">
        <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-[var(--sidebar-line)] bg-[var(--sidebar)] lg:flex">
          {brand}
          {nav}
          <div className="border-t border-[var(--sidebar-line)] px-5 py-3 text-[11px] text-[var(--sidebar-muted)]">
            {summary ? `${summary.home_bank.name} · ${summary.home_bank.code}` : "Connecting…"}
          </div>
        </aside>
  
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
            <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
            <aside className="relative flex h-full w-72 flex-col bg-[var(--sidebar)]" style={{ animation: "drawer-in 160ms ease-out" }}>
              <div className="flex items-center">
                <div className="flex-1">{brand}</div>
                <button className="mr-3 rounded p-2 text-[var(--sidebar-muted)] hover:text-[var(--sidebar-strong)]" onClick={() => setOpen(false)} aria-label="Close menu">
                  <X className="size-5" />
                </button>
              </div>
              {nav}
            </aside>
          </div>
        )}
  
        <div className="flex min-h-screen flex-col lg:pl-64">
          <div className={cx("sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-4 sm:px-6 lg:px-8", !notice && "lg:hidden")}>
            <button className="-ml-1 rounded p-2 hover:bg-[var(--surface-2)] lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
              <Menu className="size-5" />
            </button>
            <div className="flex items-center gap-2 lg:hidden">
              <div className="flex size-7 items-center justify-center rounded-[6px] bg-[var(--brand)]">
                <ShieldCheck className="size-4 text-white" />
              </div>
              <span className="font-semibold">TheOne</span>
            </div>
            <div className="flex-1" />
            {/* Only warnings appear here; the normal set-up is on the Settings page. */}
            {offline ? (
              <Badge tone="critical">Server unreachable</Badge>
            ) : summary ? (
              <div className="flex items-center gap-2">
                {summary.mode === "shadow" && (
                  <Link href="/settings" title="Scores and records only; nothing is sent to the bank">
                    <Badge tone="warning">Shadow mode: no bank actions</Badge>
                  </Link>
                )}
                {summary.bank_connector === "none" && (
                  <Link href="/settings" className="hidden sm:inline" title="Holds and blocks are recorded for manual follow-up">
                    <Badge tone="neutral">No bank connection</Badge>
                  </Link>
                )}
                {!!openAlerts && (
                  <Link href="/network/alerts" className="hidden md:inline">
                    <Badge tone="critical" icon={BellRing}>
                      {openAlerts} open alert{openAlerts > 1 ? "s" : ""}
                    </Badge>
                  </Link>
                )}
              </div>
            ) : null}
          </div>
          {/* The last block on every page stretches to the bottom of the window, so no empty background shows below it. */}
          <main className="flex flex-1 flex-col bg-[var(--canvas)] [&>:last-child]:flex-auto [&>:last-child]:pb-20">{children}</main>
          <ZivaWidget />
        </div>
      </div>
    </ZivaProvider>
  );
}

function CurrentNav(props: { openAlerts: number | null; onNavigate: () => void }) {
  return <NavLinks path={usePathname()} {...props} />;
}

function NavLinks({ path, openAlerts, onNavigate }: { path: string | null; openAlerts: number | null; onNavigate: () => void }) {
  return (
    <>
      {NAV.map((g) => (
        <div key={g.group || "top"} className="mb-4">
          {g.group && <div className="px-3 pb-1.5 text-xs font-medium text-[var(--sidebar-muted)]">{g.group}</div>}
          {g.items.map((it) => {
            const active = path != null && isActive(path, it.href);
            return (
              <Link
                key={it.href}
                href={it.href}
                onClick={onNavigate}
                className={cx(
                  "relative flex items-center gap-3 rounded-[6px] px-3 py-2 text-sm transition-colors",
                  active ? "bg-[var(--sidebar-active)] font-semibold text-[var(--sidebar-active-ink)]" : "text-[var(--sidebar-ink)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-strong)]",
                )}
                aria-current={active ? "page" : undefined}
              >
                {active && <span className="absolute left-0 top-1.5 h-[calc(100%-12px)] w-[3px] rounded-r bg-[var(--brand)]" />}
                <it.icon className="size-4 shrink-0" />
                <span className="flex-1">{it.label}</span>
                {it.badge === "alerts" && !!openAlerts && (
                  <span className="rounded-full bg-[var(--brand)] px-1.5 text-[11px] font-semibold tabular-nums text-white">{openAlerts}</span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}
