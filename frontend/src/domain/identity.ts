/** Customers and their biometrics: voice enrolment and verification, iris and device step-up. */

export type Template = {
  id: string;
  model_name: string;
  dim: number;
  sample_count: number;
  consistency: number;
  created_at: string;
  updated_at: string;
};

export type Customer = {
  id: string;
  external_id: string | null;
  display_name: string;
  language: string;
  created_at: string;
  enrolled: boolean;
  template: Template | null;
  iris_enrolled: boolean;
  iris_template: IrisTemplate | null;
};

export type IrisTemplate = {
  id: string;
  model_name: string;
  sample_count: number;
  consistency_hd: number;
  quality: Record<string, unknown>;
  created_at: string;
};

export type IrisFrame = { index: number; quality: Record<string, unknown>; hamming?: number | null };

export type IrisLiveness = {
  frames: number;
  frames_with_eye: number;
  blink_detected: boolean;
  mean_motion: number;
  static_image: boolean;
  score: number;
  model: string;
};

export type IrisEnrolResult = {
  customer_id: string;
  template: IrisTemplate;
  frames: IrisFrame[];
  liveness: IrisLiveness;
  message: string;
  warnings: string[];
};

export type IrisVerifyResult = {
  event_id: string;
  customer_id: string;
  hamming_distance: number;
  match_score: number;
  accept_hd: number;
  decision: "ACCEPT" | "REJECT";
  reasons: string[];
  liveness: IrisLiveness;
  frames: IrisFrame[];
  resolves_event_id: string | null;
};

export type Quality = {
  duration_s: number;
  sample_rate: number;
  rms_dbfs: number;
  peak_dbfs: number;
  speech_ratio: number;
  snr_db: number;
  clipped: boolean;
  ok: boolean;
  issues: string[];
};

export type Sample = {
  id: string;
  step_index: number;
  accepted: boolean;
  quality: Quality;
  spoof_score: number | null;
  message?: string | null;
};

export type EnrolmentSession = {
  id: string;
  customer_id: string;
  language: string;
  status: string;
  prompts: string[];
  required_samples: number;
  accepted_samples: number;
  next_step: number | null;
  guide: { welcome: string; step: string; done: string };
  samples: Sample[];
};

export type CompleteResult = {
  session_id: string;
  customer_id: string;
  template: Template;
  message: string;
  warnings: string[];
};

export type Decision = "ACCEPT" | "STEP_UP" | "REJECT";

export type VerifyResult = {
  event_id: string;
  customer_id: string;
  match_score: number;
  spoof_score: number;
  spoof_model: string;
  spoof_signals: Record<string, number>;
  decision: Decision;
  reasons: string[];
  quality: Quality;
  context: string | null;
};

export type ContinuousSession = {
  id: string;
  customer_id: string;
  status: "active" | "degraded" | "ended";
  ema_score: number | null;
  chunk_count: number;
  last_decision: Decision | null;
  context: string | null;
  last_event: VerifyResult | null;
};

export type VerificationEvent = {
  id: string;
  customer_id: string;
  continuous_session_id: string | null;
  context: string | null;
  modality: "voice" | "iris";
  resolves_event_id: string | null;
  match_score: number;
  spoof_score: number;
  spoof_model: string;
  decision: Decision;
  reasons: string[];
  quality: Quality;
  created_at: string;
};

export type Health = {
  status: string;
  embedder: string;
  embedding_dim: number;
  antispoof: string;
  accepted_formats: string[];
  thresholds: Record<string, number>;
};

/** What guided capture sends with each burst: the iris circle per frame, whether a blink was seen, which eye. */
export type IrisCaptureExtra = { hints?: ({ cx: number; cy: number; r: number } | null)[]; blink?: boolean; eye?: string };

export type Language = { code: string; name: string };
export type DuressEnrolResult = { message: string; frames_used: number; distance_from_normal_eye: number };
export type NewCustomer = { display_name: string; language: string; external_id?: string };

/** Where a verification happens. High-risk contexts need a closer voice match. */
export const CONTEXTS: { value: string; label: string; highRisk: boolean }[] = [
  { value: "", label: "General login", highRisk: false },
  { value: "balance_enquiry", label: "Balance enquiry", highRisk: false },
  { value: "high_value_transfer", label: "High-value transfer", highRisk: true },
  { value: "change_beneficiary", label: "Change beneficiary", highRisk: true },
  { value: "unfreeze_account", label: "Unfreeze account", highRisk: true },
  { value: "account_recovery", label: "Account recovery", highRisk: true },
];
