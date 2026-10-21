/**
 * Live eye tracking for iris capture, using MediaPipe's face landmarker (runs in the browser,
 * files served from /mediapipe so it works offline). For each video frame it gives, per eye, the
 * iris centre and radius in video pixels and how open the eye is.
 */
import type { FaceLandmarker as FL } from "@mediapipe/tasks-vision";

// The person's own left and right.
export type EyeSide = "left" | "right";
export type EyeState = { side: EyeSide; cx: number; cy: number; r: number; open: number };
export type Track = { face: boolean; eyes: EyeState[] };

// MediaPipe face mesh indices (the person's own left/right).
const IRIS = { right: { c: 468, ring: [469, 470, 471, 472] }, left: { c: 473, ring: [474, 475, 476, 477] } };
const LIDS = { right: { up: 159, down: 145, a: 33, b: 133 }, left: { up: 386, down: 374, a: 362, b: 263 } };

let shared: Promise<FL> | null = null;

/** Load the landmark model once per page. */
export function loadTracker(): Promise<FL> {
  if (!shared) {
    // MediaPipe prints start-up information through console.error ("INFO: Created TensorFlow Lite
    // XNNPACK delegate"). Drop just those lines so they don't show up as errors in the console.
    const original = console.error;
    console.error = (...args: unknown[]) => {
      if (typeof args[0] === "string" && /^INFO: |XNNPACK delegate/.test(args[0])) return;
      original(...args);
    };
    shared = (async () => {
      const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
      const files = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
      const make = (delegate: "GPU" | "CPU") =>
        FaceLandmarker.createFromOptions(files, {
          baseOptions: { modelAssetPath: "/mediapipe/face_landmarker.task", delegate },
          runningMode: "VIDEO",
          numFaces: 1,
        });
      try {
        return await make("GPU");
      } catch {
        return await make("CPU");
      }
    })();
    shared.catch(() => (shared = null));
  }
  return shared;
}

export function track(lm: FL, video: HTMLVideoElement, now: number): Track {
  const res = lm.detectForVideo(video, now);
  const pts = res.faceLandmarks?.[0];
  if (!pts || pts.length < 478) return { face: !!pts, eyes: [] };
  const W = video.videoWidth;
  const H = video.videoHeight;
  const px = (i: number) => ({ x: pts[i].x * W, y: pts[i].y * H });
  const eyes: EyeState[] = (["left", "right"] as EyeSide[]).map((side) => {
    const c = px(IRIS[side].c);
    const r = IRIS[side].ring.map((i) => Math.hypot(px(i).x - c.x, px(i).y - c.y)).reduce((a, b) => a + b, 0) / 4;
    const l = LIDS[side];
    const width = Math.hypot(px(l.a).x - px(l.b).x, px(l.a).y - px(l.b).y) || 1;
    const open = Math.hypot(px(l.up).x - px(l.down).x, px(l.up).y - px(l.down).y) / width;
    return { side, cx: c.x, cy: c.y, r, open };
  });
  return { face: true, eyes };
}

/** Square crop around the iris, at the camera's full resolution (no scaling), plus the iris circle in crop pixels. */
export async function cropEye(video: HTMLVideoElement, eye: EyeState, canvas: HTMLCanvasElement): Promise<{ blob: Blob; hint: { cx: number; cy: number; r: number }; brightness: number } | null> {
  const side = Math.round(Math.max(160, eye.r * 3.4));
  const x0 = Math.round(Math.min(Math.max(0, eye.cx - side / 2), video.videoWidth - side));
  const y0 = Math.round(Math.min(Math.max(0, eye.cy - side / 2), video.videoHeight - side));
  if (x0 < 0 || y0 < 0) return null;
  canvas.width = side;
  canvas.height = side;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(video, x0, y0, side, side, 0, 0, side, side);
  const brightness = irisBrightness(ctx, eye.cx - x0, eye.cy - y0, eye.r);
  const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", 0.96));
  return blob ? { blob, hint: { cx: eye.cx - x0, cy: eye.cy - y0, r: eye.r }, brightness } : null;
}

/** Mean brightness (0-255) of the iris area: a quick "is there enough light" check. */
export function irisBrightness(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number): number {
  const s = Math.max(4, Math.round(r));
  const d = ctx.getImageData(Math.max(0, Math.round(cx - s / 2)), Math.max(0, Math.round(cy - s / 2)), s, s).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
  return sum / (d.length / 4);
}
