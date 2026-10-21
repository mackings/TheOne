"use client";

/** The first page of the site: the onboarding film playing full screen, and one way in. */
import { ArrowRight } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const OnboardingFilm = dynamic(() => import("./OnboardingFilm").then((m) => m.OnboardingFilm), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-[var(--surface)]" />,
});

export function HomePage() {
  const [playing, setPlaying] = useState(false);
  const [seek, setSeek] = useState({ t: 0, n: 0 });

  useEffect(() => {
    const id = setTimeout(() => setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches), 400);
    return () => clearTimeout(id);
  }, []);

  // At the end, pause a moment on the last shot, then start again.
  const onEnd = useCallback(() => {
    setTimeout(() => setSeek((s) => ({ t: 0, n: s.n + 1 })), 1500);
    setPlaying(true);
  }, []);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-[var(--surface)]">
      <OnboardingFilm playing={playing} seek={seek} onEnd={onEnd} className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center pb-10 sm:pb-14">
        <Link
          href="/overview"
          className="pointer-events-auto inline-flex items-center gap-2 rounded-full bg-[var(--brand)] px-7 py-3.5 text-base font-semibold text-white shadow-lg transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)]"
        >
          Get started
          <ArrowRight className="size-4" />
        </Link>
      </div>
    </main>
  );
}
