"use client";

import { ArrowRight, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, Settings2, ShieldCheck, Skull, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, PageHeader, Segmented, Tabs } from "@/presentation/components/ui";
import { cx } from "@/presentation/cx";
import { SCENES, type Scene } from "./story";

// three.js needs the browser, so the 3D stage loads on the client only.
const TransferScene = dynamic(() => import("./TransferScene").then((m) => m.TransferScene), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-[var(--surface-2)]" />,
});

const ICON = { fraud: Skull, theone: ShieldCheck };
// Milliseconds per step.
const SPEED = { normal: 9000, slow: 13000 };

const LEGEND = [
  { swatch: "bg-[var(--info)]", label: "Message between banks" },
  { swatch: "bg-[var(--good)]", label: "Reply" },
  { swatch: "bg-[#e0a106]", label: "Money" },
  { swatch: "bg-[var(--serious)]", label: "Mule account" },
  { swatch: "bg-[var(--brand)]", label: "TheOne" },
];

type Options = { speed: keyof typeof SPEED; autoNext: boolean; legend: boolean };

export function SimulationPage() {
  const [sceneKey, setSceneKey] = useState<Scene["key"]>("fraud");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [opts, setOpts] = useState<Options>({ speed: "normal", autoNext: true, legend: true });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [viewVersion, setViewVersion] = useState(0);
  // Large screens have room for the colour key above the controls.
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const q = window.matchMedia("(min-width: 640px)");
    const on = () => setWide(q.matches);
    on();
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  const scene = SCENES.find((s) => s.key === sceneKey)!;
  const last = step === scene.steps.length - 1;
  const nextScene = SCENES[SCENES.findIndex((s) => s.key === sceneKey) + 1];

  // Play on arrival, unless the person prefers less motion.
  useEffect(() => {
    const id = setTimeout(() => setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches), 300);
    return () => clearTimeout(id);
  }, []);

  const choose = useCallback((key: Scene["key"]) => {
    setSceneKey(key);
    setStep(0);
    setPlaying(true);
  }, []);

  const onEnd = useCallback(() => {
    if (step < scene.steps.length - 1) setStep(step + 1);
    else if (opts.autoNext && nextScene) setTimeout(() => choose(nextScene.key), 1200);
    else setPlaying(false);
  }, [step, scene, opts.autoNext, nextScene, choose]);

  const go = (i: number) => setStep(Math.max(0, Math.min(scene.steps.length - 1, i)));

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight") setStep((s) => Math.min(scene.steps.length - 1, s + 1));
      else if (e.key === "ArrowLeft") setStep((s) => Math.max(0, s - 1));
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key === "Escape") setSettingsOpen(false);
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [scene]);

  return (
    <>
      <PageHeader
        title="How TheOne stops fraud"
        subtitle="Watch a scam take a customer's money through NIBSS and mule accounts, then see the same scam stopped inside the bank before the money leaves."
      />
      <Tabs<Scene["key"]>
        value={sceneKey}
        onChange={choose}
        tabs={SCENES.map((s) => ({ value: s.key, label: s.name, icon: ICON[s.key] }))}
      />

      <div className="border-b border-[var(--line)] bg-[var(--surface)]">
        {/* The stage: full width, with the step text and controls on top of it. */}
        <div className="relative h-[480px] sm:h-[600px] lg:h-[calc(100vh-230px)] lg:min-h-[620px]">
          <TransferScene
            scene={scene}
            step={step}
            playing={playing}
            onEnd={onEnd}
            stepMs={SPEED[opts.speed]}
            viewVersion={viewVersion}
            insets={{ top: 56, bottom: opts.legend && wide ? 112 : 84, right: wide && sceneKey === "theone" ? 380 : 0 }}
            className="absolute inset-0"
          />

          <div className="absolute right-4 top-4 lg:right-6 lg:top-5">
            <SettingsButton
              open={settingsOpen}
              setOpen={setSettingsOpen}
              opts={opts}
              setOpts={setOpts}
              onResetView={() => setViewVersion((v) => v + 1)}
            />
          </div>

          {opts.legend && !scene.steps[step].focus && (
            <div className="pointer-events-none absolute bottom-[76px] left-4 hidden flex-wrap gap-1.5 text-xs text-[var(--ink-2)] sm:flex lg:left-6">
              {LEGEND.map((l) => (
                <span key={l.label} className="inline-flex items-center gap-1.5 rounded-full bg-[var(--surface)] px-2 py-0.5 shadow-sm">
                  <span className={cx("size-2.5 rounded-full", l.swatch)} />
                  {l.label}
                </span>
              ))}
            </div>
          )}

          <div className="absolute inset-x-4 bottom-4 flex flex-wrap items-center gap-3 rounded-[8px] border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 shadow-md lg:inset-x-6">
            <div className="flex items-center gap-1.5">
              <Button size="sm" icon={ChevronLeft} aria-label="Previous step" disabled={step === 0} onClick={() => go(step - 1)} />
              <Button size="sm" variant="primary" icon={playing ? Pause : Play} onClick={() => setPlaying(!playing)}>
                {playing ? "Pause" : "Play"}
              </Button>
              <Button size="sm" icon={ChevronRight} aria-label="Next step" disabled={last} onClick={() => go(step + 1)} />
              <Button size="sm" variant="ghost" icon={RotateCcw} aria-label="From the start" title="From the start" onClick={() => { setStep(0); setPlaying(true); }} />
            </div>
            <ol className="flex min-w-[160px] flex-1 gap-1" aria-label="Steps">
              {scene.steps.map((s, i) => (
                <li key={s.title} className="flex-1">
                  <button
                    onClick={() => go(i)}
                    title={`${i + 1}. ${s.title}`}
                    aria-label={`Step ${i + 1}: ${s.title}`}
                    aria-current={i === step ? "step" : undefined}
                    className="group block w-full py-2"
                  >
                    <span
                      className={cx(
                        "block h-1.5 rounded-full transition-colors",
                        i < step ? "bg-[var(--ink)]" : i === step ? "bg-[var(--brand)]" : "bg-[var(--line-strong)] group-hover:bg-[var(--muted)]",
                      )}
                    />
                  </button>
                </li>
              ))}
            </ol>
            <span className="hidden text-xs tabular-nums text-[var(--muted)] sm:inline">
              {step + 1} / {scene.steps.length}
            </span>
            {last && !playing && nextScene && (
              <Button size="sm" icon={ArrowRight} onClick={() => choose(nextScene.key)}>
                {nextScene.name}
              </Button>
            )}
          </div>
        </div>

      </div>
    </>
  );
}

function SettingsButton({ open, setOpen, opts, setOpts, onResetView }: {
  open: boolean;
  setOpen: (v: boolean) => void;
  opts: Options;
  setOpts: (o: Options) => void;
  onResetView: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open, setOpen]);

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-label="Simulation settings"
        aria-expanded={open}
        title="Settings"
        className={cx(
          "flex size-9 items-center justify-center rounded-full border bg-[var(--surface)] shadow-md transition-colors",
          open ? "border-[var(--ink)] text-[var(--ink)]" : "border-[var(--line)] text-[var(--ink-2)] hover:text-[var(--ink)]",
        )}
      >
        <Settings2 className="size-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-10 w-64 rounded-[8px] border border-[var(--line)] bg-[var(--surface)] p-4 shadow-lg" role="dialog" aria-label="Simulation settings">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Settings</h3>
            <button onClick={() => setOpen(false)} aria-label="Close settings" className="text-[var(--muted)] hover:text-[var(--ink)]">
              <X className="size-4" />
            </button>
          </div>
          <div className="grid gap-3.5 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span>Speed</span>
              <Segmented<Options["speed"]>
                value={opts.speed}
                onChange={(speed) => setOpts({ ...opts, speed })}
                options={[{ value: "normal", label: "Normal" }, { value: "slow", label: "Slow" }]}
              />
            </div>
            <Toggle label="Play the next story" checked={opts.autoNext} onChange={(autoNext) => setOpts({ ...opts, autoNext })} />
            <Toggle label="Show colour key" checked={opts.legend} onChange={(legend) => setOpts({ ...opts, legend })} />
            <Button size="sm" icon={RotateCcw} onClick={onResetView}>Reset the view</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={cx("relative h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-[var(--brand)]" : "bg-[var(--line-strong)]")}
      >
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
      </button>
    </div>
  );
}
