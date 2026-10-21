import type { IdentityGateway } from "@/application/ports";
import type {
  CompleteResult,
  ContinuousSession,
  Customer,
  EnrolmentSession,
  Health,
  IrisCaptureExtra,
  IrisEnrolResult,
  IrisVerifyResult,
  Sample,
  VerificationEvent,
  VerifyResult,
} from "@/domain/identity";

import { json, request } from "./client";

function form(fields: Record<string, string | undefined>, audio?: Blob): RequestInit {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== "") fd.append(k, v);
  if (audio) fd.append("audio", audio, "clip.wav");
  return { method: "POST", body: fd };
}

export const httpIdentity: IdentityGateway = {
  health: () => request<Health>("/health"),
  languages: () => request<{ code: string; name: string }[]>("/enrolment/languages"),

  listCustomers: () => request<Customer[]>("/customers"),
  getCustomer: (id: string) => request<Customer>(`/customers/${id}`),
  createCustomer: (body: { display_name: string; language: string; external_id?: string }) =>
    request<Customer>("/customers", json(body)),
  listEvents: (id: string) => request<VerificationEvent[]>(`/customers/${id}/events`),
  revokeTemplate: (id: string) => request<void>(`/customers/${id}/template`, { method: "DELETE" }),
  revokeIrisTemplate: (id: string) => request<void>(`/customers/${id}/iris-template`, { method: "DELETE" }),

  createSession: (customer_id: string, language?: string) =>
    request<EnrolmentSession>("/enrolment/sessions", json({ customer_id, language })),
  getSession: (id: string) => request<EnrolmentSession>(`/enrolment/sessions/${id}`),
  uploadSample: (sessionId: string, step: number, audio: Blob) =>
    request<Sample>(`/enrolment/sessions/${sessionId}/samples`, form({ step_index: String(step) }, audio)),
  completeSession: (id: string) => request<CompleteResult>(`/enrolment/sessions/${id}/complete`, { method: "POST" }),

  verify: (customer_id: string, audio: Blob, context?: string) =>
    request<VerifyResult>("/verify", form({ customer_id, context }, audio)),
  startContinuous: (customer_id: string, context?: string) =>
    request<ContinuousSession>("/verify/continuous/sessions", json({ customer_id, context })),
  sendChunk: (id: string, audio: Blob) =>
    request<ContinuousSession>(`/verify/continuous/sessions/${id}/chunks`, form({}, audio)),
  endContinuous: (id: string) => request<ContinuousSession>(`/verify/continuous/sessions/${id}/end`, { method: "POST" }),

  irisEnrol: (customer_id: string, frames: Blob[], extra: IrisCaptureExtra = {}) =>
    request<IrisEnrolResult>("/iris/enrol", burst({ customer_id, ...irisFields(extra) }, frames)),
  irisDuressEnrol: (customer_id: string, frames: Blob[], extra: IrisCaptureExtra = {}) =>
    request<{ message: string; frames_used: number; distance_from_normal_eye: number }>("/iris/duress/enrol", burst({ customer_id, ...irisFields(extra) }, frames)),
  irisVerify: (customer_id: string, frames: Blob[], resolves_event_id?: string, context?: string, extra: IrisCaptureExtra = {}) =>
    request<IrisVerifyResult>("/iris/verify", burst({ customer_id, resolves_event_id, context, ...irisFields(extra) }, frames)),
};

function irisFields(x: IrisCaptureExtra): Record<string, string | undefined> {
  return { hints: x.hints ? JSON.stringify(x.hints) : undefined, blink: x.blink == null ? undefined : String(x.blink), eye: x.eye };
}

function burst(fields: Record<string, string | undefined>, frames: Blob[]): RequestInit {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v) fd.append(k, v);
  frames.forEach((b, i) => fd.append("images", b, `frame${i}.jpg`));
  return { method: "POST", body: fd };
}
