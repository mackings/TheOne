import type { AssistantGateway, LiveSession } from "@/application/ports";
import type { AssistantStatus, ChatMessage, ChatReply, LiveEvent } from "@/domain/assistant";

import { API_KEY, API_URL, json, request } from "./client";

export const httpAssistant: AssistantGateway = {
  status: () => request<AssistantStatus>("/assistant/status"),
  chat: (messages: ChatMessage[]) => request<ChatReply>("/assistant/chat", json({ messages })),
  live: (onEvent, opts) => new LiveVoice(onEvent, opts?.ring),
};

// Ziva's voice leaves the speakers and comes back in through the mic, and browsers do not reliably cancel audio played
// through Web Audio. While she speaks (and briefly after), the mic sends silence unless the analyst is clearly talking
// over her: a level of at least BARGE_IN for BARGE_IN_CHUNKS chunks in a row (128 ms each).
const BARGE_IN = 0.4;
const BARGE_IN_CHUNKS = 3;
const ECHO_TAIL_MS = 300;

function toBase64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

/**
 * One live voice session: microphone as 16 kHz PCM up to TheOne, the assistant's 24 kHz PCM
 * back out of the speakers. TheOne relays to Gemini Live, so the Gemini key never reaches
 * the browser.
 */
class LiveVoice implements LiveSession {
  private ws: WebSocket | null = null;
  private mic: AudioContext | null = null;
  private out: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private proc: ScriptProcessorNode | null = null;
  private playing = new Set<AudioBufferSourceNode>();
  private nextAt = 0;
  private echoUntil = 0;
  private loud = 0;
  level = 0;

  constructor(
    private onEvent: (e: LiveEvent) => void,
    private ring?: string,
  ) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.out = new AudioContext({ sampleRate: 24000 });
    this.mic = new AudioContext({ sampleRate: 16000 });
    await Promise.all([this.out.resume(), this.mic.resume()]);

    const params = new URLSearchParams();
    if (API_KEY) params.set("key", API_KEY);
    if (this.ring) params.set("ring", this.ring);
    const url = `${API_URL.replace(/^http/, "ws")}/assistant/live${params.size ? `?${params}` : ""}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (m) => this.handle(JSON.parse(m.data));
    this.ws.onclose = () => {
      this.onEvent({ type: "closed" });
      this.release();
    };
    await new Promise<void>((resolve, reject) => {
      this.ws!.onopen = () => resolve();
      this.ws!.onerror = () => reject(new Error("could not reach the assistant"));
    });

    const source = this.mic.createMediaStreamSource(this.stream);
    this.proc = this.mic.createScriptProcessor(2048, 1, 1);
    this.proc.onaudioprocess = (e) => {
      const f = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(f.length);
      let sum = 0;
      for (let i = 0; i < f.length; i++) {
        const v = Math.max(-1, Math.min(1, f[i]));
        pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
        sum += v * v;
      }
      this.level = Math.min(1, Math.sqrt(sum / f.length) * 4);
      const echo = this.playing.size > 0 || performance.now() < this.echoUntil;
      this.loud = echo && this.level >= BARGE_IN ? this.loud + 1 : 0;
      if (echo && this.loud < BARGE_IN_CHUNKS) pcm.fill(0);
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "audio", data: toBase64(new Uint8Array(pcm.buffer)) }));
    };
    source.connect(this.proc);
    this.proc.connect(this.mic.destination);
  }

  sendText(text: string) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "text", text }));
  }

  sendPage(page: { path: string; account?: string | null }) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "page", ...page }));
  }

  get open() {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  stop() {
    try {
      if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: "stop" }));
      this.ws?.close();
    } catch {
      /* already closed */
    }
    this.release();
  }

  private handle(m: LiveEvent & { data?: string }) {
    if (m.type === ("audio" as LiveEvent["type"]) && m.data) return this.play(m.data);
    if (m.type === "interrupted") this.silence();
    this.onEvent(m);
  }

  private play(b64: string) {
    if (!this.out) return;
    const bin = atob(b64);
    const pcm = new Int16Array(bin.length / 2);
    for (let i = 0; i < pcm.length; i++) {
      const lo = bin.charCodeAt(2 * i);
      const hi = bin.charCodeAt(2 * i + 1);
      pcm[i] = (hi << 8) | lo;
    }
    const buf = this.out.createBuffer(1, pcm.length, 24000);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 0x8000;
    const src = this.out.createBufferSource();
    src.buffer = buf;
    src.connect(this.out.destination);
    this.nextAt = Math.max(this.nextAt, this.out.currentTime + 0.03);
    src.start(this.nextAt);
    this.nextAt += buf.duration;
    if (!this.playing.size) this.onEvent({ type: "speaking", on: true });
    this.playing.add(src);
    src.onended = () => {
      this.playing.delete(src);
      if (!this.playing.size) {
        this.echoUntil = performance.now() + ECHO_TAIL_MS;
        this.onEvent({ type: "speaking", on: false });
      }
    };
  }

  private silence() {
    for (const s of this.playing) {
      try {
        s.stop();
      } catch {
        /* not started */
      }
    }
    this.playing.clear();
    this.nextAt = 0;
    this.onEvent({ type: "speaking", on: false });
  }

  private release() {
    this.silence();
    this.proc?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.mic?.close().catch(() => {});
    this.out?.close().catch(() => {});
    this.proc = null;
    this.stream = null;
    this.mic = null;
    this.out = null;
  }
}
