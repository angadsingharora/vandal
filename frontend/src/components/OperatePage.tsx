"use client";

// Step 1, Blue. The finance agent on the left with the books right under it, every Guard
// verdict in the middle, the policy and the human inbox on the right.

import { useWarRoom } from "@/lib/store";
import { ApprovalsInbox, EnforcedPolicy, OperatorPanel, RunOperations, VerdictFeed } from "./BluePanels";
import { StagePage } from "./Stage";
import { TwinPanel } from "./TwinPanel";

export function OperatePage() {
  const s = useWarRoom();
  return (
    <StagePage
      stage="operate"
      fill
      lede={
        <>
          The <span className="text-ink">Operator</span> is the finance agent doing {s.summary?.company ?? "the company"}&apos;s payables. Guard sits between
          it and the money: every tool call is checked against an independent source of truth and allowed, held, or escalated to a human.
        </>
      }
      actions={<RunOperations />}
      next={{
        label: "Attack →",
        onClick: () => void s.setStage("attack"),
        ready: s.operate.phase !== "running",
        tone: "red",
        hint:
          s.operate.phase === "done"
            ? "Next: unleash Vandal on a clone of these books."
            : s.operate.phase === "running"
              ? "The Operator is working the books…"
              : "Run operations to watch Guard at work, or go straight to attacking a clone of the seeded books.",
      }}
    >
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(440px,38%)_minmax(0,1fr)_minmax(280px,22%)] lg:grid-rows-[minmax(0,1fr)]">
        <div className="grid min-h-[70vh] min-w-0 grid-rows-[minmax(0,36%)_minmax(0,1fr)] gap-px bg-line lg:min-h-0">
          <OperatorPanel />
          <TwinPanel title="Books" />
        </div>
        <div className="flex min-h-[50vh] min-w-0 flex-col lg:min-h-0">
          <VerdictFeed />
        </div>
        <div className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-px bg-line">
          <EnforcedPolicy />
          <ApprovalsInbox />
        </div>
      </main>
    </StagePage>
  );
}
