/** HTTP access to the TheOne API: base URL, the API key header and error handling. */
import type { DocumentGateway } from "@/application/ports";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function openFromApi(path: string, download?: string) {
  const res = await fetch(`${API_URL}${path}`, { headers: API_KEY ? { "X-API-Key": API_KEY } : {} });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const url = URL.createObjectURL(await res.blob());
  if (download) {
    const a = document.createElement("a");
    a.href = url;
    a.download = download;
    a.click();
  } else {
    window.open(url, "_blank", "noopener");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const httpDocuments: DocumentGateway = { apiUrl: API_URL, open: openFromApi };
