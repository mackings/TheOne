// Copies MediaPipe's WebAssembly runtime into public/ so the iris page works offline.
// The face model (public/mediapipe/face_landmarker.task) is committed; the runtime comes from node_modules.
import { cpSync, existsSync, mkdirSync } from "node:fs";

const src = "node_modules/@mediapipe/tasks-vision/wasm";
const dst = "public/mediapipe/wasm";
if (existsSync(src)) {
  mkdirSync(dst, { recursive: true });
  cpSync(src, dst, { recursive: true });
}
