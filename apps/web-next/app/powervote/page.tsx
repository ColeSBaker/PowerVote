import { Suspense } from "react";
import { AppShell } from "@/components/app-shell";
import { PowerVotePageInner } from "@/components/powervote-page-inner";

export default function PowerVotePage() {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <PowerVotePageInner />
      </Suspense>
    </AppShell>
  );
}
