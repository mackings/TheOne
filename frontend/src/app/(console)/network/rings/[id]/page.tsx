import { Suspense } from "react";
import { RingView } from "@/presentation/features/rings/RingView";

export default function RingPage() {
  return (
    <Suspense fallback={<div className="h-40 border-b border-[var(--line)] bg-[var(--surface)]" aria-busy="true" />}>
      <RingView />
    </Suspense>
  );
}
