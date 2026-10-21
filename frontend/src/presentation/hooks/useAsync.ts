"use client";

import { useCallback, useEffect, useState } from "react";

/** Load data once, and again when `deps` change. With `every` (ms) it also refreshes quietly in the
 * background and whenever the tab comes back into view, so pages need no Refresh button. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = [], opts: { every?: number } = {}) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    fn()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e: Error) => alive && setState((s) => ({ ...s, error: e.message, loading: false })));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  useEffect(() => {
    if (!opts.every) return;
    const quiet = () => document.visibilityState === "visible" && setNonce((n) => n + 1);
    const t = setInterval(quiet, opts.every);
    document.addEventListener("visibilitychange", quiet);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", quiet);
    };
  }, [opts.every]);
  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    setNonce((n) => n + 1);
  }, []);
  return { ...state, reload };
}
