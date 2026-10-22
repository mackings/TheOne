/**
 * The two stories the simulation tells, step by step. Each step has plain words for the caption
 * and a `run` that places things in the 3D scene for a progress `p` from 0 to 1. Steps are replayed
 * from the start of the scene on every frame, so going back and forward always shows the right state.
 */

export type NodeKey = "fraudster" | "ada" | "bankA" | "theone" | "gate" | "nibss" | "bankB" | "receiver" | "mule2" | "pos";

export type Glow = "blue" | "green" | "red" | "orange" | "brand";
export type TagTone = "good" | "bad" | "info" | "brand";
export type TokenKind = "msg" | "ack" | "coin" | "stop";
export type ChipTone = "warn" | "calm" | "brand";
/** One line of TheOne's working, shown as a card. `short` replaces the title on small screens. */
export interface Card { slot: number; badge: string; title: string; detail: string; tone: ChipTone; short?: string }

export interface World {
  /** Bring in a node that is not part of the scene from the start (grows in with `p`). */
  show(key: NodeKey, p?: number): void;
  glow(key: NodeKey, color: Glow): void;
  link(a: NodeKey, b: NodeKey): void;
  /** Move a message or money token along a chain of nodes. Tokens only show during their own step,
   * unless `stay` keeps them where they ended (money that is held, for example). */
  send(id: string, path: NodeKey[], p: number, kind: TokenKind, text?: string, opts?: { fadeAtEnd?: boolean; stay?: boolean; raw?: boolean }): void;
  /** A piece of evidence: a glowing orb flies from a node into TheOne between `at[0]` and `at[1]` of the
   * step, and on arrival its card slides into the list beside TheOne. */
  sign(id: string, from: NodeKey, p: number, at: [number, number], card: Card): void;
  /** Show a card in the list beside TheOne without a flight (TheOne's own decision). */
  card(card: Card, shown: boolean): void;
  /** TheOne's risk meter, filled to `value` (0 to 1), with the flag and hold levels marked. */
  meter(value: number): void;
  tag(key: NodeKey, text: string, tone: TagTone): void;
  /** Phone-call waves from one node to another. Glows and waves only show during their own step. */
  waves(id: string, from: NodeKey, to: NodeKey, p: number, color: Glow): void;
  /** TheOne's hold: a wall between the sender's bank and NIBSS. */
  barrier(p: number): void;
}

export interface Step {
  title: string;
  body: string;
  /** Who is doing this step: the customer, the bank, NIBSS... */
  actor: string;
  /** How much longer than a normal step this one lasts (1 = normal). */
  length?: number;
  /** Bring the camera in on one node for this step (zoom below 1 is closer). */
  focus?: { on: NodeKey; zoom: number };
  run(w: World, p: number): void;
}

export interface Scene {
  key: "theone";
  name: string;
  summary: string;
  nodes: NodeKey[];
  labels: Partial<Record<NodeKey, string>>;
  steps: Step[];
}

/** Motion finishes two thirds of the way through a step; the rest leaves time to read. */
export const MOVE_END = 0.66;
export const motion = (p: number) => Math.min(1, p / MOVE_END);
const arrived = (p: number) => p >= MOVE_END;
/** Progress through the part of a step between `a` and `b`. */
const part = (p: number, a: number, b: number) => Math.min(1, Math.max(0, (p - a) / (b - a)));

// The warning signs TheOne finds on the receiving account, with the engine's own weights
// (backend/app/network/domain/engine/typologies.py). Together: 1 − (0.70 × 0.45 × 0.70 × 0.60) = 0.87.
const SIGNS = [
  { weight: 0.3, title: "Many new people paid it", detail: "9 people who never paid it before, in 2 days", short: "New payers" },
  { weight: 0.55, title: "Money left as soon as it came", detail: "96% moved on within 2 hours", short: "Left fast" },
  { weight: 0.3, title: "New account, big sums", detail: "Opened 6 days ago, already moved ₦4.4m", short: "New account" },
  { weight: 0.4, title: "Shares a phone", detail: "Same phone as 4 other accounts", short: "Shared phone" },
];
const SIGN_AT = (i: number): [number, number] => [0.04 + i * 0.11, 0.12 + i * 0.11];

/** TheOne working out its answer, one piece of evidence at a time: each sign flies in from the mule
 * account and lifts the meter, Ada's two checks follow, then the decision. */
const reckon = (w: World, p: number) => {
  let left = 1;
  SIGNS.forEach((s, i) => {
    const at = SIGN_AT(i);
    w.sign(`sign${i}`, "receiver", p, at, { slot: i, badge: `+${Math.round(s.weight * 100)}`, title: s.title, detail: s.detail, tone: "warn", short: s.short });
    if (p >= at[1]) left *= 1 - s.weight;
  });
  w.meter(1 - left);
  w.sign("adaAccount", "ada", p, [0.48, 0.55], { slot: 4, badge: "0", title: "Ada's own account", detail: "No warning signs", tone: "calm", short: "Ada's account" });
  w.sign("payment", "ada", p, [0.56, 0.63], { slot: 5, badge: "74", title: "This payment", detail: "First to this person, 12× her biggest", tone: "calm", short: "This payment" });
  w.card({ slot: 6, badge: "HOLD", title: "87 is above the hold level of 85", detail: "The money stays in Ada's bank", tone: "brand", short: "87 > 85" }, p >= 0.67);
};

const call = (w: World, p: number) => {
  w.glow("fraudster", "red");
  w.waves("call", "fraudster", "ada", p, "red");
  if (p > 0.5) w.tag("ada", "“Send it to a safe account”", "bad");
};

export const SCENE: Scene = {
  key: "theone",
  name: "Fraud with TheOne",
  summary: "A fraudster talks Ada into paying a mule account, but Ada's bank asks TheOne before the money leaves.",
  nodes: ["fraudster", "ada", "bankA", "nibss", "bankB", "receiver"],
  labels: {
    fraudster: "Fraudster", ada: "Ada", bankA: "Ada's bank", nibss: "NIBSS", bankB: "Bank B",
    receiver: "“Safe account”", theone: "TheOne",
  },
  steps: [
    {
      actor: "Fraudster",
      title: "A call that sounds like her bank",
      body: "A fraudster calls Ada: “This is your bank. Your account has been hacked. Move your money to this safe account now.”",
      run: call,
    },
    {
      actor: "Ada's bank → NIBSS",
      title: "The name check happens as usual",
      body: "Ada enters the account and ₦850,000. Her bank runs the name check through NIBSS and a real name comes back. Nothing has left yet.",
      run: (w, p) => {
        w.link("ada", "bankA");
        w.link("bankA", "nibss");
        w.link("nibss", "bankB");
        w.send("ne", ["bankA", "nibss", "bankB", "nibss", "bankA"], p, "msg", "Name check");
      },
    },
    {
      actor: "Ada's bank → TheOne",
      title: "Before sending, the bank asks TheOne",
      body: "Between the name check and the payment, Ada's bank asks TheOne: is it safe to send ₦850,000 to this account?",
      run: (w, p) => {
        w.show("theone", p);
        w.link("bankA", "theone");
        w.send("ask", ["bankA", "theone"], p, "msg", "Safe to send?");
      },
    },
    {
      actor: "TheOne",
      length: 2.6,
      focus: { on: "theone", zoom: 0.9 },
      title: "TheOne works out the risk",
      body: "Each warning sign on the receiving account adds to its risk score: 87 out of 100, above the hold level of 85. Ada's account and the payment are checked too. The answer: hold.",
      run: (w, p) => {
        w.glow("theone", "brand");
        w.glow("receiver", "orange");
        reckon(w, p);
        w.send("answer", ["theone", "bankA"], part(p, 0.72, 0.94), "stop", "HOLD", { raw: true });
      },
    },
    {
      actor: "Ada's bank",
      title: "The money is held",
      body: "Ada's bank does not send the payment. The ₦850,000 never leaves her bank, so there is nothing to chase.",
      run: (w, p) => {
        w.barrier(p);
        w.send("held", ["ada", "bankA", "gate"], p, "coin", "₦850,000", { stay: true });
        if (arrived(p)) w.tag("bankA", "Payment held", "brand");
      },
    },
    {
      actor: "Ada's bank → Ada",
      title: "Ada is warned in time",
      body: "Her app tells her the payment is on hold because it looks like a scam, and the fraud team calls her on a number they trust.",
      run: (w, p) => {
        w.send("warn", ["bankA", "ada"], p, "ack", "This looks like a scam");
        if (arrived(p)) w.tag("ada", "Safe: ₦850,000 kept", "good");
      },
    },
  ],
};
