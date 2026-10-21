"use client";

/** The composition root: the real HTTP gateways are chosen here and nowhere else. */
import { httpGateways } from "@/infrastructure/http";
import { GatewayProvider } from "@/presentation/hooks/gateways";

export function Providers({ children }: { children: React.ReactNode }) {
  return <GatewayProvider gateways={httpGateways}>{children}</GatewayProvider>;
}
