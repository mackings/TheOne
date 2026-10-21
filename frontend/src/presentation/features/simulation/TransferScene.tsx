"use client";

/** The 3D stage for the transfer simulation (three.js). It draws whatever the current story step
 * describes, and plays each step's motion when `playing`; when a step finishes it calls `onEnd`. */
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { bank, ease, label, mat, nibssHub, palette, type Palette, person, popIn, shield, withFloor } from "@/presentation/three/models";
import { type Card, type ChipTone, type Glow, motion, MOVE_END, type NodeKey, type Scene, type TagTone, type TokenKind, type World } from "./story";

// Where each thing stands on the ground (x, z), and the height messages leave from.
const SPOT: Record<NodeKey, { x: number; z: number; top: number }> = {
  fraudster: { x: -10.6, z: -3.8, top: 1.7 },
  ada: { x: -9.2, z: 3, top: 1.7 },
  bankA: { x: -5, z: 0, top: 2.1 },
  theone: { x: -5, z: -5.4, top: 2.4 },
  gate: { x: -2.6, z: 0, top: 1.2 },
  nibss: { x: 0, z: 0, top: 1.0 },
  bankB: { x: 5, z: 0, top: 2.1 },
  receiver: { x: 9.8, z: 3, top: 1.7 },
  mule2: { x: 12.4, z: -1.6, top: 1.7 },
  pos: { x: 9.6, z: -5, top: 1.1 },
};
const KEYS = Object.keys(SPOT) as NodeKey[];
// Half the scene's width (labels included) and depth, for fitting it on screen.
const HALF_W = 13.2;
const HALF_D = 6.2;

const glowColor = (pal: Palette, g: Glow) => ({ blue: pal.info, green: pal.good, red: pal.critical, orange: pal.serious, brand: pal.brand })[g];

function buildNode(key: NodeKey, pal: Palette): THREE.Group {
  switch (key) {
    case "ada":
      return person(pal.info);
    case "receiver":
      return person("#3f8f5a");
    case "mule2":
      return person(pal.serious);
    case "fraudster": {
      const g = person("#2e2e30");
      const phone = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.34, 0.06), mat(pal.critical, { emissive: pal.critical, emissiveIntensity: 0.6 }));
      phone.position.set(0.36, 1.35, 0.15);
      g.add(phone);
      return g;
    }
    case "bankA":
      return bank("#3b5fb0", pal);
    case "bankB":
      return bank("#2f8f83", pal);
    case "nibss":
      return nibssHub(pal);
    case "pos": {
      const g = new THREE.Group();
      const box = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.75, 0.55), mat("#3a3a3c"));
      box.position.y = 0.38;
      const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.3), mat(pal.good, { emissive: pal.good, emissiveIntensity: 0.6 }));
      screen.position.set(0, 0.5, 0.28);
      g.add(box, screen);
      return g;
    }
    case "theone":
      return shield(pal);
    case "gate":
      return new THREE.Group();
  }
}

const TAG_CLASS: Record<TagTone, string> = {
  good: "bg-[var(--good)] text-white",
  bad: "bg-[var(--critical)] text-white",
  info: "bg-[var(--info)] text-white",
  brand: "bg-[var(--brand)] text-white",
};

/** Curve a link or token follows from one node to the next. */
function curve(a: NodeKey, b: NodeKey) {
  const A = SPOT[a];
  const B = SPOT[b];
  const start = new THREE.Vector3(A.x, A.top, A.z);
  const end = new THREE.Vector3(B.x, B.top, B.z);
  const lift = 0.8 + start.distanceTo(end) * 0.1;
  const mid = start.clone().add(end).multiplyScalar(0.5).add(new THREE.Vector3(0, lift, 0));
  return new THREE.QuadraticBezierCurve3(start, mid, end);
}

export function TransferScene({ scene, step, playing, onEnd, onProgress, stepMs = 9000, viewVersion = 0, insets, className }: {
  scene: Scene;
  step: number;
  playing: boolean;
  onEnd: () => void;
  /** Called every frame with how far through the current step it is (0 to 1). */
  onProgress?: (p: number) => void;
  /** How long one step lasts, in milliseconds. */
  stepMs?: number;
  /** Change it to put the camera back where it started. */
  viewVersion?: number;
  /** Space (px) covered by the page's own panels; the scene is fitted into what is left. */
  insets?: { top: number; bottom: number; right?: number };
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const refit = useRef<() => void>(() => {});
  const state = useRef({ scene, step, playing, onEnd, onProgress, stepMs, progress: playing ? 0 : 1, ended: false });
  const pad = useRef({ top: insets?.top ?? 0, bottom: insets?.bottom ?? 0, right: insets?.right ?? 0 });

  // A new step starts from the beginning when playing, or shows its end state when paused.
  useEffect(() => {
    const s = state.current;
    const moved = s.scene !== scene || s.step !== step;
    s.scene = scene;
    s.step = step;
    s.onEnd = onEnd;
    s.onProgress = onProgress;
    s.stepMs = stepMs;
    if (moved) {
      s.progress = playing ? 0 : 1;
      s.ended = !playing;
    } else if (playing && !s.playing && s.progress >= 1) {
      // Pressing play on a finished step replays it.
      s.progress = 0;
      s.ended = false;
    }
    s.playing = playing;
  }, [scene, step, playing, onEnd, onProgress, stepMs]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const pal = withFloor(palette());
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setClearColor(pal.surface);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    // Soft shadows, and tone mapping that keeps the brand colours true.
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.VSMShadowMap;
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = 1;
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.domElement.style.position = "absolute";
    labels.domElement.style.inset = "0";
    labels.domElement.style.pointerEvents = "none";
    // Keeps the labels' stacking inside the stage, below the page's controls.
    labels.domElement.style.zIndex = "0";
    el.appendChild(labels.domElement);

    const world3 = new THREE.Scene();
    // The far floor fades into the page instead of ending in an edge.
    const fog = new THREE.Fog(pal.surface, 60, 120);
    world3.fog = fog;
    const camera = new THREE.PerspectiveCamera(38, 2, 0.1, 200);
    const target = new THREE.Vector3(0.3, 0.6, -1.8);
    const controls = new OrbitControls(camera, renderer.domElement);
    // Pinch to zoom on touch screens; the mouse wheel keeps scrolling the page.
    const keepWheel = (e: WheelEvent) => e.stopPropagation();
    el.addEventListener("wheel", keepWheel, { capture: true });
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.minPolarAngle = 0.35;
    controls.maxPolarAngle = 1.15;
    controls.minAzimuthAngle = -0.7;
    controls.maxAzimuthAngle = 0.7;
    controls.target.copy(target);
    // Where the camera looks and how close it is; steps with a focus ease these towards one node.
    const camTarget = target.clone();
    let camZoom = 1;
    let baseBack = 30;

    // A soft studio environment gives every surface realistic reflections (coins, glass, roofs).
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    world3.environment = envTexture;
    world3.environmentIntensity = 0.35;
    world3.add(new THREE.HemisphereLight("#ffffff", "#9a978f", 0.55));
    const sun = new THREE.DirectionalLight("#fff6e8", 1.7);
    sun.position.set(-8, 18, 10);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.radius = 8;
    sun.shadow.blurSamples = 16;
    sun.shadow.bias = -0.0004;
    Object.assign(sun.shadow.camera, { left: -20, right: 20, top: 12, bottom: -12 });
    world3.add(sun);
    const ground = new THREE.Mesh(new THREE.CircleGeometry(90, 64), new THREE.MeshStandardMaterial({ color: pal.ground, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    world3.add(ground);
    const grid = new THREE.GridHelper(80, 40, pal.grid, pal.grid);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.6;
    grid.position.y = 0.01;
    world3.add(grid);

    // Nodes, each with a glow ring, a name label and a callout tag.
    const nodes = {} as Record<NodeKey, { group: THREE.Group; ring: THREE.Mesh; name: CSS2DObject; tag: CSS2DObject; tagText: string; tagTone: string }>;
    for (const key of KEYS) {
      const s = SPOT[key];
      const group = buildNode(key, pal);
      group.position.set(s.x, 0, s.z);
      group.traverse((o) => o instanceof THREE.Mesh && (o.castShadow = true));
      const ring = new THREE.Mesh(new THREE.RingGeometry(1.55, 1.85, 48), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.4, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(s.x, 0.02, s.z);
      const name = label("whitespace-nowrap rounded-[4px] border border-[var(--line)] bg-[var(--surface)] px-2 py-0.5 text-[12px] font-semibold text-[var(--ink)] shadow-sm");
      // Names sit in front of a node; TheOne's shield is tall, so its name goes on top instead.
      const tall = key === "theone";
      name.center.set(0.5, tall ? 1 : 0);
      name.position.set(s.x, tall ? s.top + 0.55 : 0, tall ? s.z : s.z + 1.55);
      const tag = label("max-w-[150px] rounded-[6px] px-2.5 py-1 text-center text-[11px] font-semibold leading-snug shadow-md sm:max-w-[220px] sm:text-[12px]");
      // A tall shield keeps its name on top, so its callout goes to the side. Callouts near the left
      // or right edge grow inwards so they stay on screen.
      if (tall) tag.center.set(0, 0.5);
      else if (s.x < -10.5) tag.center.set(0.15, 1);
      else if (s.x > 10.5) tag.center.set(0.85, 1);
      tag.position.set(tall ? s.x + 1.1 : s.x, tall ? s.top - 0.6 : s.top + 0.75, s.z);
      world3.add(group, ring, name, tag);
      nodes[key] = { group, ring, name, tag, tagText: "", tagTone: "" };
    }

    const links = new Map<string, THREE.Mesh>();
    const linkMat = new THREE.MeshStandardMaterial({ color: pal.line.clone().lerp(pal.ink, 0.25), roughness: 1 });
    const getLink = (a: NodeKey, b: NodeKey) => {
      const id = `${a}-${b}`;
      let m = links.get(id);
      if (!m) {
        m = new THREE.Mesh(new THREE.TubeGeometry(curve(a, b), 48, 0.05, 8, false), linkMat);
        world3.add(m);
        links.set(id, m);
      }
      return m;
    };

    const tokens = new Map<string, { group: THREE.Group; body: THREE.Mesh; text: CSS2DObject; kind: TokenKind; trail: THREE.Mesh[] }>();
    const TRAIL = 9;
    const trailGeo = new THREE.SphereGeometry(0.13, 12, 8);
    const makeTrail = (color: THREE.Color) =>
      Array.from({ length: TRAIL }, (_, k) => {
        const m = new THREE.Mesh(trailGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5 * (1 - k / TRAIL), depthWrite: false }));
        m.scale.setScalar(1 - k / (TRAIL + 2));
        world3.add(m);
        return m;
      });
    /** A point `d` along a chain of curves (clamped to its ends). */
    const along = (legs: THREE.QuadraticBezierCurve3[], lengths: number[], d: number) => {
      let leg = 0;
      let rest = Math.max(0, d);
      while (leg < legs.length - 1 && rest > lengths[leg]) rest -= lengths[leg++];
      return legs[leg].getPointAt(Math.min(1, rest / lengths[leg]));
    };

    // Ripples on the ground where something arrives.
    const ripples = new Map<string, THREE.Mesh>();
    const ripple = (id: string, at: THREE.Vector3, r: number, color: THREE.Color) => {
      if (r <= 0 || r >= 1) return;
      let m = ripples.get(id);
      if (!m) {
        m = new THREE.Mesh(new THREE.RingGeometry(0.9, 1.05, 48), new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false }));
        m.rotation.x = -Math.PI / 2;
        world3.add(m);
        ripples.set(id, m);
      }
      m.visible = true;
      m.position.set(at.x, 0.04, at.z);
      m.scale.setScalar(0.6 + ease(r) * 2.2);
      const mm = m.material as THREE.MeshBasicMaterial;
      mm.color.copy(color);
      mm.opacity = 0.75 * (1 - r);
    };
    const tokenGeo = {
      msg: new THREE.BoxGeometry(0.6, 0.4, 0.07),
      coin: new THREE.CylinderGeometry(0.34, 0.34, 0.12, 32),
      stop: new THREE.CylinderGeometry(0.42, 0.42, 0.1, 8),
    };
    const getToken = (id: string, kind: TokenKind) => {
      let t = tokens.get(id);
      if (!t) {
        const color = kind === "coin" ? pal.gold : kind === "ack" ? pal.good : kind === "stop" ? pal.brand : pal.info;
        const geo = kind === "coin" ? tokenGeo.coin : kind === "stop" ? tokenGeo.stop : tokenGeo.msg;
        const body = new THREE.Mesh(geo, mat(color, { emissive: color, emissiveIntensity: kind === "coin" ? 0.12 : 0.35, metalness: kind === "coin" ? 0.85 : 0.05, roughness: kind === "coin" ? 0.25 : 0.45 }));
        if (kind === "coin" || kind === "stop") body.rotation.x = Math.PI / 2;
        body.castShadow = true;
        const text = label("whitespace-nowrap rounded-[4px] bg-[var(--ink)] px-1.5 py-0.5 text-[11px] font-semibold text-[var(--surface)] shadow");
        text.position.y = 0.55;
        const group = new THREE.Group();
        group.add(body, text);
        world3.add(group);
        t = { group, body, text, kind, trail: makeTrail(color) };
        tokens.set(id, t);
      }
      return t;
    };

    const waves = new Map<string, THREE.Mesh[]>();
    const getWaves = (id: string) => {
      let w = waves.get(id);
      if (!w) {
        w = Array.from({ length: 3 }, () => {
          const m = new THREE.Mesh(new THREE.TorusGeometry(0.45, 0.04, 8, 32), new THREE.MeshBasicMaterial({ transparent: true }));
          world3.add(m);
          return m;
        });
        waves.set(id, w);
      }
      return w;
    };

    const wallMat = new THREE.MeshStandardMaterial({ color: pal.brand, transparent: true, opacity: 0.45, emissive: pal.brand, emissiveIntensity: 0.5, depthWrite: false });
    const wall = new THREE.Mesh(new THREE.BoxGeometry(0.3, 3, 4), wallMat);
    const wallEdge = new THREE.LineSegments(new THREE.EdgesGeometry(wall.geometry), new THREE.LineBasicMaterial({ color: pal.brand }));
    wall.add(wallEdge);
    wall.position.set(SPOT.gate.x + 0.55, 1.5, 0);
    world3.add(wall);

    // TheOne's working: evidence orbs fly into the shield, and a list of cards builds up beside it.
    const orbs = new Map<string, { core: THREE.Mesh; halo: THREE.Mesh; trail: THREE.Mesh[] }>();
    const orbGeo = new THREE.SphereGeometry(0.22, 24, 16);
    const haloGeo = new THREE.SphereGeometry(0.42, 24, 16);
    const getOrb = (id: string, color: THREE.Color) => {
      let o = orbs.get(id);
      if (!o) {
        const core = new THREE.Mesh(orbGeo, new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 1.2 }));
        const halo = new THREE.Mesh(haloGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25, depthWrite: false }));
        world3.add(core, halo);
        o = { core, halo, trail: makeTrail(color) };
        orbs.set(id, o);
      }
      return o;
    };
    const shieldCentre = new THREE.Vector3(SPOT.theone.x, 1.6, SPOT.theone.z);

    // Every card has its own place from the start, so each one lands in position and nothing shifts.
    // TheOne's checks get their own clear column at the right edge of the stage (the scene is framed to
    // leave it free), so the cards never cover the animation. Phones show only the newest card, small.
    const rail = document.createElement("div");
    rail.className = "pointer-events-none absolute flex flex-col justify-center";
    const railHead = document.createElement("div");
    railHead.className = "mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--ink)]";
    railHead.innerHTML = '<span class="size-2 rounded-full bg-[var(--brand)]"></span>What TheOne found';
    const railList = document.createElement("div");
    railList.className = "flex flex-col gap-2";
    rail.append(railHead, railList);
    el.appendChild(rail);
    const board = { element: railList, visible: false };
    const placeRail = () => {
      const { top, bottom, right } = pad.current;
      Object.assign(rail.style, right > 0
        ? { left: "", right: "20px", width: `${right - 40}px`, top: `${top}px`, bottom: `${bottom}px` }
        : { left: "12px", right: "", width: "170px", top: "12px", bottom: "" });
      railHead.style.display = right > 0 ? "" : "none";
    };
    const BADGE: Record<ChipTone, string> = { warn: "bg-[var(--serious)]", calm: "bg-[var(--good)]", brand: "bg-white !text-[var(--brand)]" };
    const cardEls: HTMLDivElement[] = [];
    const cardKeys: string[] = [];
    const getCardEl = (slot: number) => {
      while (cardEls.length <= slot) {
        const d = document.createElement("div");
        board.element.appendChild(d);
        cardEls.push(d);
        cardKeys.push("");
      }
      return cardEls[slot];
    };
    let compact = false;
    let newest = -1;
    const putCard = (c: Card, shown: boolean) => {
      const d = getCardEl(c.slot);
      const key = `${c.badge}|${c.title}|${c.detail}|${compact}`;
      if (cardKeys[c.slot] !== key) {
        cardKeys[c.slot] = key;
        const size = compact ? "h-7 min-w-7 text-[11px]" : "h-10 min-w-10 text-[13px]";
        const badge = `<span class="flex ${size} shrink-0 items-center justify-center rounded-full px-2 font-bold text-white shadow-inner ${BADGE[c.tone]}">${c.badge}</span>`;
        const text = compact
          ? `<span class="text-[12px] font-semibold leading-tight">${c.short ?? c.title}</span>`
          : `<span class="min-w-0"><span class="block text-[13px] font-semibold leading-snug">${c.title}</span><span class="block truncate text-[12px] leading-snug opacity-80">${c.detail}</span></span>`;
        d.innerHTML = badge + text;
      }
      if (shown) newest = Math.max(newest, c.slot);
      d.dataset.shown = shown ? "1" : "";
    };
    const CARD_BASE = "flex items-center gap-2.5 rounded-[10px] px-2.5 py-1.5 shadow-lg ring-1 transition-all duration-700 ease-out sm:gap-3 sm:px-3 sm:py-2";
    const styleCards = () => {
      rail.style.visibility = board.visible ? "visible" : "hidden";
      cardEls.forEach((d, i) => {
        const on = d.dataset.shown === "1";
        const brand = cardKeys[i].startsWith("HOLD");
        const tone = brand ? "bg-[var(--brand)] text-white ring-[var(--brand)]" : "bg-[var(--surface)] text-[var(--ink)] ring-[var(--line)]";
        // Small screens keep only the newest card; large screens keep every card in its slot.
        const state = compact
          ? i === newest ? "opacity-100 translate-x-0" : "hidden"
          : on ? "opacity-100 translate-x-0 scale-100" : "invisible opacity-0 -translate-x-8 scale-95";
        const cls = `${CARD_BASE} ${tone} ${state}`;
        if (d.className !== cls) d.className = cls;
      });
    };

    const meter = new THREE.Group();
    const M = { x: SPOT.theone.x - 2.6, z: SPOT.theone.z, h: 4.2 };
    meter.position.set(M.x, 0, M.z);
    const glass = new THREE.Mesh(
      new THREE.CylinderGeometry(0.46, 0.46, M.h, 32, 1, true),
      new THREE.MeshStandardMaterial({ color: "#ffffff", transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }),
    );
    glass.position.y = M.h / 2;
    const fillGeo = new THREE.CylinderGeometry(0.38, 0.38, 1, 32);
    fillGeo.translate(0, 0.5, 0);
    const fillMat = mat(pal.serious, { emissive: pal.serious, emissiveIntensity: 0.35 });
    const fill = new THREE.Mesh(fillGeo, fillMat);
    const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.68, 0.16, 32), mat("#3a3a3c"));
    foot.position.y = 0.07;
    meter.add(glass, fill, foot);
    for (const [at, text] of [[0.6, "flag 60"], [0.85, "hold 85"]] as const) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.5, 0.035, 8, 32), new THREE.MeshBasicMaterial({ color: at === 0.85 ? pal.brand : pal.ink }));
      ring.rotation.x = Math.PI / 2;
      ring.position.y = at * M.h;
      const mark = label("whitespace-nowrap text-[10px] font-semibold text-[var(--muted)]");
      mark.center.set(1, 0.5);
      mark.position.set(-0.62, at * M.h, 0);
      mark.element.textContent = text;
      meter.add(ring, mark);
    }
    const reading = label("whitespace-nowrap rounded-[6px] bg-[var(--ink)] px-2 py-0.5 text-[12px] font-semibold text-[var(--surface)] shadow");
    reading.position.set(0, M.h + 0.35, 0);
    meter.add(reading);
    world3.add(meter);
    let meterTarget = 0;
    let meterShown = 0;

    let time = 0;
    const setText = (o: CSS2DObject, text: string) => {
      if (o.element.textContent !== text) o.element.textContent = text;
    };

    // Draw the scene for (scene, step, progress): reset, replay earlier steps at their end, then this one.
    function draw(sc: Scene, stepIndex: number, progress: number) {
      const shown = new Set<NodeKey>(sc.nodes);
      for (const key of KEYS) {
        const n = nodes[key];
        n.group.visible = shown.has(key);
        n.group.scale.setScalar(n.group.userData.scale ?? 1);
        n.ring.visible = false;
        n.tag.visible = false;
        n.tagText = "";
      }
      links.forEach((m) => (m.visible = false));
      tokens.forEach((t) => {
        t.group.visible = false;
        // Labels are drawn separately, so hide them with their token.
        t.text.visible = false;
      });
      waves.forEach((w) => w.forEach((m) => (m.visible = false)));
      wall.visible = false;
      orbs.forEach((o) => [o.core, o.halo, ...o.trail].forEach((m) => (m.visible = false)));
      ripples.forEach((m) => (m.visible = false));
      tokens.forEach((t) => t.trail.forEach((m) => (m.visible = false)));
      compact = pad.current.right <= 0;
      newest = -1;
      cardEls.forEach((d) => (d.dataset.shown = ""));
      board.visible = false;
      meter.visible = false;
      meter.children.forEach((o) => o instanceof CSS2DObject && (o.visible = false));

      let past = true;
      const world: World = {
        show(key, p = 1) {
          const g = nodes[key].group;
          g.visible = true;
          shown.add(key);
          g.scale.setScalar((g.userData.scale ?? 1) * (past ? 1 : Math.max(0.001, popIn(Math.min(1, p * 1.6)))));
        },
        glow(key, color) {
          if (past) return;
          const r = nodes[key].ring;
          r.visible = true;
          (r.material as THREE.MeshBasicMaterial).color.copy(glowColor(pal, color));
          (r.material as THREE.MeshBasicMaterial).opacity = 0.3 + 0.2 * Math.sin(time * 2.2);
        },
        link(a, b) {
          getLink(a, b).visible = true;
        },
        send(id, path, p, kind, text, opts) {
          if (past && !opts?.stay) return;
          const t = getToken(id, kind);
          const m = past ? 1 : opts?.raw ? ease(p) : ease(motion(p));
          if (opts?.raw && !past && p <= 0) return;
          const legs = path.slice(1).map((b, i) => curve(path[i], b));
          const lengths = legs.map((c) => c.getLength());
          const total = lengths.reduce((a, b) => a + b, 0);
          t.group.position.copy(along(legs, lengths, m * total));
          t.group.visible = true;
          // A fading trail behind anything on the move, and a ripple where it lands.
          if (!past && m > 0 && m < 1) {
            t.trail.forEach((g, k) => {
              g.visible = true;
              g.position.copy(along(legs, lengths, m * total - (k + 1) * 0.32));
            });
          }
          if (!past && !opts?.raw && !opts?.fadeAtEnd) {
            const last = path[path.length - 1];
            ripple(id, new THREE.Vector3(SPOT[last].x, 0, SPOT[last].z), (p - MOVE_END) / 0.12, (t.body.material as THREE.MeshStandardMaterial).color);
          }
          const fade = opts?.fadeAtEnd && !past ? Math.max(0, 1 - Math.max(0, p - MOVE_END - 0.04) / 0.12) : 1;
          t.group.scale.setScalar(fade);
          if (t.kind === "coin") t.body.rotation.z = time * 1.4;
          if (t.kind === "msg" || t.kind === "ack") t.body.rotation.y = Math.sin(time * 1.2) * 0.3;
          t.text.visible = !!text && fade > 0.5;
          if (text) setText(t.text, text);
        },
        tag(key, text, tone) {
          const n = nodes[key];
          n.tag.visible = true;
          setText(n.tag, text);
          const cls = `max-w-[150px] rounded-[6px] px-2.5 py-1 text-center text-[11px] font-semibold leading-snug shadow-md sm:max-w-[220px] sm:text-[12px] ${TAG_CLASS[tone]}`;
          if (n.tag.element.className !== cls) n.tag.element.className = cls;
        },
        waves(id, from, to, p, color) {
          if (past) return;
          const a = new THREE.Vector3(SPOT[from].x, SPOT[from].top, SPOT[from].z);
          const b = new THREE.Vector3(SPOT[to].x, SPOT[to].top, SPOT[to].z);
          getWaves(id).forEach((m, i) => {
            const f = (((time * 0.35 + i / 3) % 1) + 1) % 1;
            const on = motion(p) < 1 || p < 0.95;
            m.visible = on;
            m.position.lerpVectors(a, b, f);
            m.lookAt(b);
            m.scale.setScalar(0.6 + f * 0.9);
            const mm = m.material as THREE.MeshBasicMaterial;
            mm.color.copy(glowColor(pal, color));
            mm.opacity = Math.sin(f * Math.PI) * 0.9;
          });
        },
        sign(id, from, p, at, c) {
          const t = past ? 1 : Math.min(1, Math.max(0, (p - at[0]) / (at[1] - at[0])));
          board.visible = true;
          putCard(c, t >= 1);
          if (past || t <= 0) return;
          const color = c.tone === "calm" ? pal.good : pal.serious;
          if (t < 1) {
            const o = getOrb(id, color);
            const start = new THREE.Vector3(SPOT[from].x, SPOT[from].top, SPOT[from].z);
            const mid = start.clone().add(shieldCentre).multiplyScalar(0.5).add(new THREE.Vector3(0, 2.2 + start.distanceTo(shieldCentre) * 0.1, 0));
            const path = new THREE.QuadraticBezierCurve3(start, mid, shieldCentre);
            const e = ease(t);
            o.core.visible = o.halo.visible = true;
            o.core.position.copy(path.getPoint(e));
            o.halo.position.copy(o.core.position);
            o.halo.scale.setScalar(1 + 0.25 * Math.sin(time * 9));
            o.trail.forEach((g, k) => {
              g.visible = true;
              g.position.copy(path.getPoint(Math.max(0, e - (k + 1) * 0.025)));
            });
          }
          ripple(`${id}-hit`, shieldCentre, (p - at[1]) / 0.06, color);
        },
        card(c, shown) {
          board.visible = true;
          putCard(c, shown);
        },
        meter(value) {
          meter.visible = true;
          meter.children.forEach((o) => o instanceof CSS2DObject && (o.visible = true));
          meterTarget = value;
        },
        barrier(p) {
          wall.visible = true;
          wall.scale.y = past ? 1 : Math.max(0.001, popIn(Math.min(1, p * 1.8)));
          wallMat.opacity = 0.4 + 0.1 * Math.sin(time * 1.8);
        },
      };
      sc.steps.forEach((s, i) => {
        if (i > stepIndex) return;
        past = i < stepIndex;
        s.run(world, past ? 1 : progress);
      });
      styleCards();
      for (const key of KEYS) {
        const n = nodes[key];
        const text = sc.labels[key];
        n.name.visible = n.group.visible && !!text && key !== "gate";
        if (text) setText(n.name, text);
      }
    }

    function fit() {
      const w = el!.clientWidth;
      const h = el!.clientHeight;
      renderer.setSize(w, h);
      labels.setSize(w, h);
      placeRail();
      camera.aspect = w / h;
      // Back off until every node, with its label, fits: the width usually decides, the depth on tall screens.
      // About 63° above the ground.
      const elev = 1.1;
      // Only the band between the page's top and bottom panels is free, so fit into that.
      const { top, bottom, right } = pad.current;
      const free = Math.max(0.35, (h - top - bottom) / h);
      const freeW = Math.max(0.4, (w - right) / w);
      const half = THREE.MathUtils.degToRad(camera.fov / 2);
      const byWidth = HALF_W / (Math.tan(half) * camera.aspect * freeW);
      const byDepth = (HALF_D * Math.sin(elev) + 2) / (Math.tan(half) * free);
      const back = Math.max(byWidth, byDepth) * 1.04;
      baseBack = back;
      // Fog only on the far horizon, well beyond the scene, so the floor keeps its own colour.
      fog.near = back * 1.45;
      fog.far = back * 2.6;
      controls.target.copy(camTarget);
      camera.position.copy(camTarget).add(new THREE.Vector3(0, Math.sin(elev), Math.cos(elev)).multiplyScalar(back * camZoom));
      // Shift the picture so the scene sits in the middle of the free space.
      camera.setViewOffset(w, h, right / 2, (bottom - top) / 2, w, h);
      controls.minDistance = back * 0.45;
      controls.maxDistance = back * 1.2;
      camera.updateProjectionMatrix();
      controls.update();
    }
    refit.current = fit;
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    fit();

    const timer = new THREE.Timer();
    // No time jump after the tab was hidden.
    timer.connect(document);
    let raf = 0;
    const loop = (now?: number) => {
      raf = requestAnimationFrame(loop);
      timer.update(now);
      const dt = Math.min(0.1, timer.getDelta());
      time += dt;
      const s = state.current;
      if (s.playing && s.progress < 1) {
        s.progress = Math.min(1, s.progress + (dt * 1000) / (s.stepMs * (s.scene.steps[s.step]?.length ?? 1)));
        if (s.progress >= 1 && !s.ended) {
          s.ended = true;
          s.onEnd();
        }
      }
      const spin = nodes.nibss.group.userData.spin as THREE.Mesh;
      spin.rotation.z += dt * 0.4;
      (nodes.nibss.group.userData.core as THREE.Mesh).rotation.y += dt * 0.3;
      const float = nodes.theone.group.userData.float as THREE.Mesh;
      float.position.y = 1.55 + Math.sin(time * 1.2) * 0.08;
      float.rotation.y = Math.sin(time * 0.5) * 0.3;
      const focus = s.scene.steps[s.step]?.focus;
      // Lean towards the focus mostly sideways, so the people at the front stay in view.
      const wantTarget = focus
        ? target.clone().add(new THREE.Vector3((SPOT[focus.on].x - target.x) * 0.22, 0, (SPOT[focus.on].z - target.z) * 0.12))
        : target;
      const wantZoom = focus ? focus.zoom : 1;
      if (camTarget.distanceTo(wantTarget) > 0.004 || Math.abs(camZoom - wantZoom) > 0.0005) {
        const k = Math.min(1, dt * 1.1);
        const dir = camera.position.clone().sub(controls.target).normalize();
        camTarget.lerp(wantTarget, k);
        camZoom += (wantZoom - camZoom) * k;
        controls.target.copy(camTarget);
        camera.position.copy(camTarget).addScaledVector(dir, baseBack * camZoom);
      }
      draw(s.scene, s.step, s.progress);
      if (meter.visible) {
        meterShown += (meterTarget - meterShown) * Math.min(1, dt * 3);
        fill.scale.y = Math.max(0.001, meterShown * M.h);
        fillMat.color.copy(meterShown >= 0.85 ? pal.brand : meterShown >= 0.6 ? pal.serious : pal.gold);
        fillMat.emissive.copy(fillMat.color);
        setText(reading, `Risk ${Math.round(meterShown * 100)} / 100`);
      } else meterShown = 0;
      s.onProgress?.(s.progress);
      controls.update();
      renderer.render(world3, camera);
      labels.render(world3, camera);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      timer.dispose();
      el.removeEventListener("wheel", keepWheel, { capture: true });
      ro.disconnect();
      controls.dispose();
      world3.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
          o.geometry.dispose();
          const m = o.material as THREE.Material | THREE.Material[];
          (Array.isArray(m) ? m : [m]).forEach((x) => x.dispose());
        }
      });
      envTexture.dispose();
      pmrem.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      el.removeChild(labels.domElement);
      el.removeChild(rail);
    };
  }, []);

  useEffect(() => {
    if (viewVersion) refit.current();
  }, [viewVersion]);
  const top = insets?.top ?? 0;
  const bottom = insets?.bottom ?? 0;
  const right = insets?.right ?? 0;
  useEffect(() => {
    pad.current = { top, bottom, right };
    refit.current();
  }, [top, bottom, right]);

  // The caller places the stage (absolute, fixed height...); it defaults to relative so labels can sit on it.
  return <div ref={host} className={`overflow-hidden ${className ?? "relative"}`} />;
}
