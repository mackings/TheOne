"use client";

/** Dependency injection for pages: the composition root provides the gateways, pages ask for the one they need. */
import { createContext, useContext } from "react";

import type { Gateways } from "@/application/ports";

const GatewayContext = createContext<Gateways | null>(null);

export function GatewayProvider({ gateways, children }: { gateways: Gateways; children: React.ReactNode }) {
  return <GatewayContext.Provider value={gateways}>{children}</GatewayContext.Provider>;
}

function useGateways(): Gateways {
  const g = useContext(GatewayContext);
  if (!g) throw new Error("GatewayProvider is missing above this component");
  return g;
}

export const useNetwork = () => useGateways().network;
export const useIdentity = () => useGateways().identity;
export const useAssistant = () => useGateways().assistant;
export const useDocuments = () => useGateways().documents;
