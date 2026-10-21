/** The analyst assistant: chat replies, console actions it asks for, and live voice events. */

export type UiAction = { navigate?: string };

export type ChatReply = { reply: string; steps: string[]; ui: UiAction[]; model?: string };

export type LiveEvent =
  | { type: "ready" }
  | { type: "user_text" | "assistant_text" | "step" | "error"; text: string }
  | { type: "ui"; action: UiAction }
  | { type: "turn_complete" | "interrupted" | "closed" }
  | { type: "speaking"; on: boolean };

export type ChatMessage = { role: "user" | "assistant"; text: string };
export type AssistantStatus = { enabled: boolean; text_model: string; live_model: string };
