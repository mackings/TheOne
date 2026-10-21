"use client";

import { useState } from "react";

const KEY = "theone.actor";

/** The analyst's name for the audit trail, remembered on this browser only. */
export function useActor(): [string, (v: string) => void] {
  const [actor, setActorState] = useState<string>(() => {
    try {
      return (typeof window !== "undefined" && window.localStorage.getItem(KEY)) || "analyst";
    } catch {
      return "analyst";
    }
  });
  const setActor = (v: string) => {
    setActorState(v);
    try {
      window.localStorage.setItem(KEY, v);
    } catch {
      /* storage unavailable: keep in memory */
    }
  };
  return [actor, setActor];
}
