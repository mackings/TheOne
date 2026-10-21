/**
 * Microphone capture to 16-bit PCM WAV, done in the browser so the backend
 * never needs ffmpeg. We ask the AudioContext for 16 kHz; browsers that ignore
 * that (older Safari) record at their native rate and the backend resamples.
 */
export class Recorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private proc: ScriptProcessorNode | null = null;
  private chunks: Float32Array[] = [];
  private _level = 0;

  get sampleRate(): number {
    return this.ctx?.sampleRate ?? 16000;
  }

  /** Instantaneous input level 0..1, for a meter. */
  get level(): number {
    return this._level;
  }

  get active(): boolean {
    return this.ctx !== null;
  }

  async start(): Promise<void> {
    if (this.ctx) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: false, autoGainControl: true },
    });
    this.ctx = new AudioContext({ sampleRate: 16000 });
    await this.ctx.resume();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.proc = this.ctx.createScriptProcessor(4096, 1, 1);
    this.proc.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      this.chunks.push(new Float32Array(data));
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      this._level = Math.min(1, Math.sqrt(sum / data.length) * 6);
    };
    this.source.connect(this.proc);
    this.proc.connect(this.ctx.destination);
    this.chunks = [];
  }

  /** Return everything captured since the last take, as WAV, without stopping. */
  take(): Blob {
    const chunks = this.chunks;
    this.chunks = [];
    return encodeWav(chunks, this.sampleRate);
  }

  /** Stop capture and return the full recording as WAV. */
  async stop(): Promise<Blob> {
    const blob = this.take();
    this.proc?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    await this.ctx?.close();
    this.proc = this.source = this.stream = this.ctx = null;
    this._level = 0;
    return blob;
  }
}

export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  const n = chunks.reduce((a, c) => a + c.length, 0);
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  str(0, "RIFF");
  v.setUint32(4, 36 + n * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, "data");
  v.setUint32(40, n * 2, true);
  let o = 44;
  for (const c of chunks) {
    for (let i = 0; i < c.length; i++, o += 2) {
      const s = Math.max(-1, Math.min(1, c[i]));
      v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
  }
  return new Blob([buf], { type: "audio/wav" });
}
