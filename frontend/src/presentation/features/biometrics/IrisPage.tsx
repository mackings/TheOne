"use client";

import Link from "next/link";
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { FaceLandmarker } from "@mediapipe/tasks-vision";

import { cropEye, type EyeSide, type EyeState, irisBrightness, loadTracker, track } from "@/infrastructure/media/irisTracker";
import { Button, Card, DecisionBadge, ErrorText, ScoreBar } from "./parts";
import type { Customer, IrisEnrolResult, IrisVerifyResult } from "@/domain/identity";
import { useIdentity } from "@/presentation/hooks/gateways";

// Guided capture. Radii are camera pixels: the server refuses an iris under 36 px, so the guide asks
// for 42. Capture starts after 12 good checks in a row (about 0.4 s) and sends 10 open-eye frames.
const MIN_R = 36;
const TARGET_R = 42;
const GOOD_STREAK = 12;
const BURST = 10;
const MAX_CAPTURE_MS = 4500;

/** Monotonic time for the capture loop (which runs outside rendering). */
const clock = () => performance.now();

type Phase = "off" | "loading" | "aim" | "capturing" | "sending";
type Guide = { text: string; tone: "bad" | "warn" | "good"; size: number };

export function IrisPage() {
  return (
    <Suspense fallback={null}>
      <IrisInner />
    </Suspense>
  );
}

function IrisInner() {
  const api = useIdentity();
  const params = useSearchParams();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState(params.get("customer") ?? "");
  const [mode, setMode] = useState<"enrol" | "verify" | "duress">((params.get("mode") as "enrol" | "verify" | "duress") ?? "verify");
  const resolves = params.get("resolves");
  const context = params.get("context") ?? undefined;
  const [phase, setPhase] = useState<Phase>("off");
  const [guide, setGuide] = useState<Guide>({ text: "Turn on the camera to start", tone: "warn", size: 0 });
  const [progress, setProgress] = useState(0);
  const [blinkPrompt, setBlinkPrompt] = useState(false);
  const [enrolResult, setEnrolResult] = useState<IrisEnrolResult | null>(null);
  const [verifyResult, setVerifyResult] = useState<IrisVerifyResult | null>(null);
  const [duressNote, setDuressNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const overlay = useRef<HTMLCanvasElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const tracker = useRef<FaceLandmarker | null>(null);
  const raf = useRef(0);
  const state = useRef({ phase: "off" as Phase, streak: 0, last: null as EyeState | null, bright: 128, n: 0 });
  const selected = customers.find((c) => c.id === customerId);
  const enrolledEye = (selected?.iris_template?.quality as { eye?: EyeSide } | undefined)?.eye;
  const busy = phase === "capturing" || phase === "sending";
  // The capture loop runs outside React renders, so it reads the current choices from here.
  const cfg = useRef({ mode, enrolledEye, customerId, selected });
  useEffect(() => {
    cfg.current = { mode, enrolledEye, customerId, selected };
  }, [mode, enrolledEye, customerId, selected]);
  const setP = (p: Phase) => {
    state.current.phase = p;
    setPhase(p);
  };

  useEffect(() => {
    api
      .listCustomers()
      .then((cs) => {
        setCustomers(cs);
        if (cs.length === 1) setCustomerId((cur) => cur || cs[0].id);
      })
      .catch((e) => setError(e.message));
    const s = stream;
    const r = raf;
    return () => {
      cancelAnimationFrame(r.current);
      s.current?.getTracks().forEach((t) => t.stop());
      s.current = null;
    };
  }, [api]);

  /** Which eye to use: the other eye for the duress signal, otherwise the bigger (closer) one. */
  function pickEye(eyes: EyeState[]): EyeState | null {
    const { mode, enrolledEye } = cfg.current;
    if (!eyes.length) return null;
    if (mode === "duress" && enrolledEye) return eyes.find((e) => e.side !== enrolledEye) ?? null;
    if (mode === "verify" && enrolledEye) return eyes.find((e) => e.side === enrolledEye) ?? null;
    return [...eyes].sort((a, b) => b.r - a.r)[0];
  }

  function judge(eye: EyeState | null, face: boolean): Guide & { ok: boolean } {
    const st = state.current;
    const { mode, selected, customerId } = cfg.current;
    if (!customerId) return { text: "Select a customer first", tone: "bad", size: 0, ok: false };
    if (mode === "verify" && selected && !selected.iris_enrolled) return { text: "Enrol this customer's iris first", tone: "bad", size: 0, ok: false };
    if (!face) return { text: "Look straight at the camera", tone: "bad", size: 0, ok: false };
    if (!eye) return { text: mode === "duress" ? "Show your other eye" : "Show the same eye you enrolled", tone: "bad", size: 0, ok: false };
    const size = Math.min(1, eye.r / TARGET_R);
    if (eye.r < MIN_R) return { text: "Move closer to the camera", tone: "bad", size, ok: false };
    if (eye.r < TARGET_R) return { text: "A little closer", tone: "warn", size, ok: false };
    if (eye.open < 0.2) return { text: "Open your eye wide", tone: "warn", size, ok: false };
    if (st.last && Math.hypot(eye.cx - st.last.cx, eye.cy - st.last.cy) > 0.12 * eye.r) return { text: "Hold still", tone: "warn", size, ok: false };
    if (st.bright < 55) return { text: "Add light: face a window or a lamp", tone: "warn", size, ok: false };
    if (st.bright > 225) return { text: "Too bright: move away from the light", tone: "warn", size, ok: false };
    return { text: "Good. Hold still", tone: "good", size, ok: true };
  }

  function draw(eye: EyeState | null, tone: Guide["tone"]) {
    const v = video.current;
    const c = overlay.current;
    if (!v || !c) return;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (c.width !== w) c.width = w;
    if (c.height !== h) c.height = h;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, w, h);
    if (!eye || !v.videoWidth) return;
    // The video is shown mirrored and cropped to fill (object-cover); map camera pixels to the box.
    const k = Math.max(w / v.videoWidth, h / v.videoHeight);
    const ox = (w - v.videoWidth * k) / 2;
    const oy = (h - v.videoHeight * k) / 2;
    const x = w - (eye.cx * k + ox);
    const y = eye.cy * k + oy;
    ctx.lineWidth = 3;
    ctx.strokeStyle = tone === "good" ? "#22c55e" : tone === "warn" ? "#f59e0b" : "#ef4444";
    ctx.beginPath();
    ctx.arc(x, y, eye.r * k, 0, Math.PI * 2);
    ctx.stroke();
  }

  async function startCamera() {
    setError(null);
    setP("loading");
    setGuide({ text: "Starting camera and eye tracker…", tone: "warn", size: 0 });
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 }, facingMode: "user" },
        audio: false,
      });
      if (video.current) {
        video.current.srcObject = stream.current;
        await video.current.play();
      }
      tracker.current = await loadTracker();
      setP("aim");
      loop();
    } catch (err) {
      setP("off");
      setError(`Camera or eye tracker unavailable: ${(err as Error).message}`);
    }
  }

  function stopCamera() {
    cancelAnimationFrame(raf.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    setP("off");
    setGuide({ text: "Turn on the camera to start", tone: "warn", size: 0 });
    draw(null, "bad");
  }

  const probe = useRef<HTMLCanvasElement | null>(null);
  function loop() {
    const v = video.current;
    const lm = tracker.current;
    const st = state.current;
    if (v && lm && v.readyState >= 2 && (st.phase === "aim" || st.phase === "capturing")) {
      const t = track(lm, v, clock());
      const eye = pickEye(t.eyes);
      if (eye && st.n++ % 6 === 0) {
        const c = (probe.current ??= document.createElement("canvas"));
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        const ctx = c.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(v, 0, 0);
        st.bright = irisBrightness(ctx, eye.cx, eye.cy, eye.r);
      }
      const g = judge(eye, t.face);
      st.last = eye;
      if (st.phase === "aim") {
        setGuide(g);
        st.streak = g.ok ? st.streak + 1 : 0;
        if (st.streak >= GOOD_STREAK) {
          st.streak = 0;
          void capture(eye!.side);
        }
      }
      draw(eye, st.phase === "capturing" ? "good" : g.tone);
    }
    raf.current = requestAnimationFrame(loop);
  }

  /** Collect open-eye frames for a few seconds, ask for one blink, then send the burst. */
  async function capture(side: EyeSide) {
    const { mode, customerId, selected } = cfg.current;
    const v = video.current;
    const lm = tracker.current;
    if (!v || !lm || state.current.phase !== "aim") return;
    if (mode === "verify" && selected && !selected.iris_enrolled) {
      setError(`${selected.display_name} has no iris template yet. Switch to "Enrol iris" first.`);
      return;
    }
    setError(null);
    setEnrolResult(null);
    setVerifyResult(null);
    setDuressNote(null);
    setP("capturing");
    setProgress(0);
    setGuide({ text: "Capturing. Keep looking at the camera", tone: "good", size: 1 });
    const canvas = document.createElement("canvas");
    const frames: Blob[] = [];
    const hints: { cx: number; cy: number; r: number }[] = [];
    const opens: number[] = [];
    let baseline = 0;
    let closed = false;
    let blink = false;
    const t0 = clock();
    let lastShot = 0;
    while (clock() - t0 < MAX_CAPTURE_MS && (frames.length < BURST || (!blink && clock() - t0 < MAX_CAPTURE_MS))) {
      await new Promise((r) => requestAnimationFrame(r));
      const eye = track(lm, v, clock()).eyes.find((e) => e.side === side);
      if (!eye) continue;
      opens.push(eye.open);
      if (opens.length === 6) baseline = [...opens].sort((a, b) => a - b)[3];
      if (baseline) {
        if (eye.open < baseline * 0.55) closed = true;
        else if (closed && eye.open > baseline * 0.8) blink = true;
      }
      if (frames.length >= 3 && !blink) setBlinkPrompt(true);
      if (blink) setBlinkPrompt(false);
      const open = !baseline || eye.open >= baseline * 0.8;
      if (frames.length < BURST && open && eye.r >= MIN_R && clock() - lastShot > 110) {
        const shot = await cropEye(v, eye, canvas);
        if (shot) {
          frames.push(shot.blob);
          hints.push(shot.hint);
          lastShot = clock();
          setProgress(frames.length / BURST);
        }
      }
    }
    setBlinkPrompt(false);
    if (frames.length < 4) {
      setP("aim");
      setError("The eye moved out of view during capture. Hold still and it will try again.");
      return;
    }
    setP("sending");
    setGuide({ text: mode === "verify" ? "Matching…" : "Saving…", tone: "good", size: 1 });
    const extra = { hints, blink, eye: side };
    try {
      if (mode === "duress") {
        const r = await api.irisDuressEnrol(customerId, frames, extra);
        setDuressNote(r.message);
        api.listCustomers().then(setCustomers).catch(() => {});
      } else if (mode === "enrol") {
        setEnrolResult(await api.irisEnrol(customerId, frames, extra));
        api.listCustomers().then(setCustomers).catch(() => {});
      } else {
        setVerifyResult(await api.irisVerify(customerId, frames, resolves ?? undefined, context, extra));
      }
      stopCamera();
    } catch (err) {
      setError((err as Error).message);
      setP("aim");
    }
  }

  return (
    <div className="flex flex-col [&>:last-child]:mb-0 [&>:last-child]:flex-auto">
      {resolves && (
        <Card>
          <p className="text-sm">
            <span className="font-semibold text-[var(--warn)]">Step-up verification.</span> The voice check asked for a
            second factor{context ? ` for "${context.replace(/_/g, " ")}"` : ""}. A successful iris match will be
            recorded against that voice decision.
          </p>
        </Card>
      )}

      <Card title="Eye scan">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1 text-sm">
            Customer
            <select
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              disabled={busy}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              <option value="">Select a customer</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                  {c.iris_enrolled ? " · iris enrolled" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            Mode
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "enrol" | "verify" | "duress")}
              disabled={busy || Boolean(resolves)}
              className="h-10 rounded-[6px] border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:border-[var(--brand)]"
            >
              <option value="enrol">Enrol iris</option>
              <option value="verify">Verify iris</option>
              <option value="duress">Set up duress eye (other eye)</option>
            </select>
          </label>
        </div>
        {!customerId && customers.length > 0 && (
          <p className="mt-2 text-sm text-[var(--warn)]">Select a customer to enable capture.</p>
        )}
        {customers.length === 0 && !error && (
          <p className="mt-2 text-sm text-[var(--warn)]">
            No customers yet. <Link href="/enrol" className="underline">Create one on the Enrol page</Link> first.
          </p>
        )}
        {mode === "duress" && (
          <p className="mt-2 text-sm">
            Capture the customer&apos;s <b>other</b> eye. If they are ever forced to approve a payment, they show this eye: the
            screen shows success, but the transfer is held and the fraud desk is alerted.
          </p>
        )}
        {selected?.iris_template && selected.iris_template.consistency_hd > 0.31 && (
          <p className="mt-2 text-sm text-[var(--warn)]">
            This customer&apos;s iris enrolment is poor quality (frames {selected.iris_template.consistency_hd.toFixed(2)} apart), so it will not
            match reliably. Switch to &quot;Enrol iris&quot; and enrol again; the guided capture replaces it.
          </p>
        )}
        {mode === "verify" && selected && !selected.iris_enrolled && (
          <p className="mt-2 text-sm text-[var(--warn)]">This customer has no iris template yet. Switch to enrol first.</p>
        )}

        <div className="relative mx-auto mt-5 w-full max-w-2xl overflow-hidden rounded-[8px] bg-black" style={{ aspectRatio: "16 / 9" }}>
          <video ref={video} muted playsInline className="h-full w-full object-cover" style={{ transform: "scaleX(-1)" }} />
          <canvas ref={overlay} className="pointer-events-none absolute inset-0 h-full w-full" />
          {phase === "off" && <div className="absolute inset-0 flex items-center justify-center text-sm text-white/80">Camera off</div>}
          {phase !== "off" && (
            <div className="absolute inset-x-0 top-0 flex justify-center p-3">
              <span
                className="rounded-full px-4 py-1.5 text-sm font-semibold text-white shadow"
                style={{ background: guide.tone === "good" ? "#16a34a" : guide.tone === "warn" ? "#d97706" : "#dc2626" }}
                role="status"
                aria-live="polite"
              >
                {blinkPrompt ? "Blink once now" : guide.text}
              </span>
            </div>
          )}
          {phase === "aim" && (
            <div className="absolute inset-x-6 bottom-4">
              <div className="mb-1 flex justify-between text-[11px] font-medium text-white/85">
                <span>Distance</span>
                <span>{guide.size >= 1 ? "Close enough" : "Move closer"}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/25">
                <div className="h-1.5 rounded-full transition-[width] duration-150" style={{ width: `${Math.round(guide.size * 100)}%`, background: guide.size >= 1 ? "#22c55e" : "#f59e0b" }} />
              </div>
            </div>
          )}
          {phase === "capturing" && (
            <div className="absolute bottom-0 left-0 h-1.5 bg-[var(--good)] transition-[width]" style={{ width: `${progress * 100}%` }} />
          )}
        </div>
        <ul className="mx-auto mt-3 grid max-w-2xl gap-1 text-sm text-[var(--muted)] sm:grid-cols-3">
          <li>1. Face a window or a lamp, so your eye is well lit.</li>
          <li>2. Bring one eye close until the bar turns green.</li>
          <li>3. Hold still. It captures by itself; blink once when asked.</li>
        </ul>

        <div className="mt-4 flex justify-center gap-3">
          {phase === "off" ? (
            <Button onClick={startCamera} disabled={!customerId}>Turn on camera</Button>
          ) : (
            <Button variant="secondary" onClick={stopCamera} disabled={busy}>
              {phase === "loading" ? "Starting…" : busy ? (phase === "sending" ? "Matching…" : "Capturing…") : "Stop camera"}
            </Button>
          )}
        </div>
        <ErrorText error={error} />
      </Card>

      {duressNote && (
        <Card title="Danger eye saved">
          <p>{duressNote}</p>
        </Card>
      )}

      {enrolResult && (
        <Card title="Iris set up">
          <p>{enrolResult.message}</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-[var(--muted)]">Frames used</dt>
            <dd>{enrolResult.template.sample_count} of {enrolResult.frames.length}</dd>
            <dt className="text-[var(--muted)]">Frame consistency (distance)</dt>
            <dd>{enrolResult.template.consistency_hd.toFixed(3)}</dd>
            <dt className="text-[var(--muted)]">Iris radius</dt>
            <dd>{String(enrolResult.template.quality.iris_radius_px)} px</dd>
            <dt className="text-[var(--muted)]">Blink seen</dt>
            <dd>{enrolResult.liveness.blink_detected ? "yes" : "no"}</dd>
          </dl>
          {enrolResult.warnings.map((w) => (
            <p key={w} className="mt-2 text-sm text-[var(--warn)]">{w}</p>
          ))}
          <FrameList frames={enrolResult.frames} />
        </Card>
      )}

      {verifyResult && (
        <Card title="Result">
          <div className="mb-4 flex items-center gap-4">
            <DecisionBadge decision={verifyResult.decision as "ACCEPT" | "REJECT"} />
            <span className="text-sm text-[var(--muted)]">
              {verifyResult.decision === "ACCEPT"
                ? resolves
                  ? "Step-up satisfied. The original action can proceed."
                  : "Iris matches the enrolled template."
                : "Iris does not match, or the capture was unusable."}
            </span>
          </div>
          <ScoreBar
            label="Iris match (1 − Hamming distance)"
            value={verifyResult.match_score}
            marks={[{ at: 1 - verifyResult.accept_hd, label: "accept" }]}
          />
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {verifyResult.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Liveness: {verifyResult.liveness.frames_with_eye}/{verifyResult.liveness.frames} frames with an eye · blink{" "}
            {verifyResult.liveness.blink_detected ? "seen" : "not seen"} · motion {verifyResult.liveness.mean_motion}
          </p>
          <FrameList frames={verifyResult.frames} />
          {resolves && (
            <div className="mt-4">
              <Link href={`/customers`} className="text-sm text-[var(--brand)] underline">
                View the linked events in the customer history
              </Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function FrameList({ frames }: { frames: { index: number; quality: Record<string, unknown>; hamming?: number | null }[] }) {
  return (
    <details className="mt-3 text-xs text-[var(--muted)]">
      <summary className="cursor-pointer">Per-frame detail</summary>
      <table className="mt-2 w-full">
        <thead>
          <tr className="text-left">
            <th>#</th>
            <th>eye</th>
            <th>iris</th>
            <th>focus</th>
            <th>radius</th>
            <th>coverage</th>
            <th>distance</th>
          </tr>
        </thead>
        <tbody>
          {frames.map((f) => (
            <tr key={f.index} className="border-t border-[var(--border)]">
              <td>{f.index}</td>
              <td>{String(f.quality.eye_found)}</td>
              <td>{String(f.quality.iris_found)}</td>
              <td>{String(f.quality.focus)}</td>
              <td>{String(f.quality.iris_radius_px)}</td>
              <td>{String(f.quality.mask_coverage)}</td>
              <td>{f.hamming == null ? "–" : f.hamming.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
