/** The home film (how a bank brings in TheOne): chapters, how long each lasts, and where the camera stands. */

export type Vec = [number, number, number];

export interface Chapter {
  key: "intro" | "data" | "check" | "act" | "learn" | "stages";
  seconds: number;
  camera: { pos: Vec; target: Vec };
}

export const CHAPTERS: Chapter[] = [
  { key: "intro", seconds: 6, camera: { pos: [-0.5, 25, 31], target: [-0.5, 0, 2] } },
  { key: "data", seconds: 10, camera: { pos: [0.5, 17, 23], target: [0.5, 1, -1] } },
  { key: "check", seconds: 12, camera: { pos: [-2.5, 17.5, 24], target: [-2.5, 1, -1.5] } },
  { key: "act", seconds: 9, camera: { pos: [0.5, 15, 21], target: [0.5, 1, -0.5] } },
  { key: "learn", seconds: 9, camera: { pos: [-3, 18, 21], target: [-3, 1, -4] } },
  { key: "stages", seconds: 22, camera: { pos: [-7, 15, 32], target: [-5.5, 1, 11] } },
];

export const TOTAL = CHAPTERS.reduce((s, c) => s + c.seconds, 0);

/** Which chapter is playing at time `t`, and how far through it (0 to 1). */
export function at(t: number) {
  let start = 0;
  for (let i = 0; i < CHAPTERS.length; i++) {
    const c = CHAPTERS[i];
    if (t < start + c.seconds || i === CHAPTERS.length - 1) return { index: i, chapter: c, start, p: Math.min(1, Math.max(0, (t - start) / c.seconds)) };
    start += c.seconds;
  }
  throw new Error("unreachable");
}

/** The four rollout stages the road passes through. */
export const STAGES = ["Replay", "Live, test mode", "Live, limited", "Full protection"];
