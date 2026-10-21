import type { Gateways } from "@/application/ports";

import { httpAssistant } from "./assistant";
import { httpDocuments } from "./client";
import { httpIdentity } from "./identity";
import { httpNetwork } from "./network";

/** The real backend, over HTTP and WebSocket. */
export const httpGateways: Gateways = {
  network: httpNetwork,
  identity: httpIdentity,
  assistant: httpAssistant,
  documents: httpDocuments,
};
