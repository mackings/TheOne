import { AppShell } from "@/presentation/components/shell/AppShell";

/** Every console page shares the sidebar, top bar and assistant. The first page (/) sits outside it. */
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
