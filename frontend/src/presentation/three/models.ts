/** Shared three.js pieces for the console's 3D scenes: colours from the page's theme, materials, and the
 * low-poly models (people, banks, NIBSS, TheOne's shield). */
import * as THREE from "three";
import { CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";

export function css(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function palette() {
  return {
    brand: new THREE.Color(css("--brand", "#d71920")),
    info: new THREE.Color(css("--info", "#2f5fb3")),
    good: new THREE.Color(css("--good", "#0ca30c")),
    serious: new THREE.Color(css("--serious", "#ec835a")),
    critical: new THREE.Color(css("--critical", "#d03b3b")),
    surface: new THREE.Color(css("--surface", "#ffffff")),
    line: new THREE.Color(css("--line", "#e4e4e4")),
    ink: new THREE.Color(css("--ink", "#1f1f1f")),
    gold: new THREE.Color("#e0a106"),
    building: new THREE.Color("#ffffff"),
  };
}
export type Palette = ReturnType<typeof palette> & { ground: THREE.Color; grid: THREE.Color; edge: THREE.Color };

/** The floor is a clear step darker than the page (lighter in dark mode), so white buildings stand out. */
export function withFloor(p: ReturnType<typeof palette>): Palette {
  return {
    ...p,
    ground: p.surface.clone().lerp(p.ink, 0.3),
    grid: p.surface.clone().lerp(p.ink, 0.42),
    edge: p.surface.clone().lerp(p.ink, 0.55),
  };
}

/** Thin outlines along a mesh's edges, so shapes read clearly against the floor. */
export function outline(mesh: THREE.Mesh, color: THREE.Color) {
  const lines = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 30), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 }));
  mesh.add(lines);
  return mesh;
}

export const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const popIn = (t: number) => {
  const c = 1.7;
  const x = Math.min(1, Math.max(0, t));
  return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2);
};

export function mat(color: THREE.Color | string, extra: THREE.MeshStandardMaterialParameters = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.75, metalness: 0.05, ...extra });
}

export function person(color: THREE.Color | string) {
  const g = new THREE.Group();
  g.userData.scale = 1.25;
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.34, 0.62, 6, 16), mat(color));
  body.position.y = 0.66;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.27, 24, 16), mat("#f1c9a5"));
  head.position.y = 1.43;
  g.add(body, head);
  return g;
}

export function bank(roof: THREE.Color | string, pal: Palette) {
  const g = new THREE.Group();
  // A darker plinth under each bank separates it from the floor.
  const base = outline(new THREE.Mesh(new THREE.BoxGeometry(3.3, 0.2, 2.6), mat("#8f949c")), pal.edge);
  base.position.y = 0.1;
  const body = outline(new THREE.Mesh(new THREE.BoxGeometry(2.6, 1.3, 1.9), mat(pal.building, { roughness: 0.55 })), pal.edge);
  body.position.y = 0.85;
  g.add(base, body);
  for (const x of [-0.85, -0.28, 0.28, 0.85]) {
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 1.2, 12), mat("#ffffff"));
    col.position.set(x, 0.8, 1.02);
    g.add(col);
  }
  const top = new THREE.Mesh(new THREE.ConeGeometry(2.05, 0.75, 4), mat(roof));
  top.rotation.y = Math.PI / 4;
  top.scale.set(1, 1, 0.72);
  top.position.y = 1.86;
  g.add(top);
  return g;
}

export function shield(pal: Palette) {
  const s = new THREE.Shape();
  s.moveTo(0, 0.95);
  s.quadraticCurveTo(0.45, 0.82, 0.8, 0.85);
  s.lineTo(0.8, 0.1);
  s.quadraticCurveTo(0.75, -0.6, 0, -0.95);
  s.quadraticCurveTo(-0.75, -0.6, -0.8, 0.1);
  s.lineTo(-0.8, 0.85);
  s.quadraticCurveTo(-0.45, 0.82, 0, 0.95);
  const geo = new THREE.ExtrudeGeometry(s, { depth: 0.22, bevelEnabled: true, bevelSize: 0.05, bevelThickness: 0.05, bevelSegments: 2 });
  geo.center();
  const g = new THREE.Group();
  const m = new THREE.Mesh(geo, mat(pal.brand, { emissive: pal.brand, emissiveIntensity: 0.25 }));
  m.position.y = 1.55;
  const tick = new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.07, 8, 24, Math.PI * 1.25), mat("#ffffff"));
  tick.position.set(0, 1.55, 0.2);
  tick.rotation.z = -Math.PI / 2.4;
  const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.6, 8), mat("#9a9a96"));
  post.position.y = 0.3;
  g.add(m, tick, post);
  g.userData.float = m;
  return g;
}

export function nibssHub(pal: Palette) {
  const g = new THREE.Group();
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(1.7, 1.85, 0.45, 48), mat("#2b2d31"));
  plate.position.y = 0.23;
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 1), mat(pal.info, { emissive: pal.info, emissiveIntensity: 0.5, flatShading: true }));
  core.position.y = 0.95;
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.05, 8, 64), mat(pal.info, { emissive: pal.info, emissiveIntensity: 0.8 }));
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.6;
  g.add(plate, core, ring);
  g.userData.spin = ring;
  g.userData.core = core;
  return g;
}

export function label(className: string) {
  const el = document.createElement("div");
  el.className = className;
  const obj = new CSS2DObject(el);
  obj.center.set(0.5, 1);
  return obj;
}
