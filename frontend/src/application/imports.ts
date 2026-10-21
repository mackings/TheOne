/** How a bank file gets in: small files inline, large NIP and CSV files as background jobs. */
import type { ImportJob } from "@/domain/network";

export const BACKGROUND_FROM_BYTES = 40 * 1024 * 1024;
const STREAMABLE = new Set(["nip", "csv"]);

export type ImportRoute = "inline" | "background" | "too_large";

export function importRoute(format: string, bytes: number): ImportRoute {
  if (bytes <= BACKGROUND_FROM_BYTES) return "inline";
  return STREAMABLE.has(format) ? "background" : "too_large";
}

export const jobFinished = (job: ImportJob) => job.status === "done" || job.status === "failed";
