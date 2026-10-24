"use client";

import { useEffect, useState } from "react";
import { useWarRoom } from "@/lib/store";
import { ApprovalsInbox, OperatorPanel, VerdictFeed } from "./BluePanels";
import { ChainView } from "./ChainView";
import { ExplainDrawer } from "./ExplainDrawer";
import { InjectDialog } from "./InjectDialog";
import { ScorecardDialog } from "./ScorecardDialog";
import { SearchPanel } from "./SearchPanel";
import { SynthesisPanel } from "./SynthesisPanel";
import { TopBar } from "./TopBar";
import { TwinPanel } from "./TwinPanel";

/** DESIGN §14: Red's search on the left, the twin and its authorization chains in the middle,
 * the Operator, Blue's verdicts, and the approvals inbox on the right, synthesis along the
 * bottom. */
export function WarRoom() {
  const init = useWarRoom((s) => s.init);
  const error = useWarRoom((s) => s.error);
  const clearError = useWarRoom((s) => s.clearError);
  const ready = useWarRoom((s) => s.ready);
  const [dialog, setDialog] = useState<"inject" | "scorecard" | null>(null);

  useEffect(() => {
    void init();
  }, [init]);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      <TopBar onInject={() => setDialog("inject")} onScorecard={() => setDialog("scorecard")} />
      {error && (
        <div role="alert" className="flex items-center gap-3 border-b border-bad/40 bg-bad/10 px-4 py-1.5 text-xs text-bad">
          <span className="font-semibold">Error</span>
          <span className="min-w-0 flex-1 truncate">{error}</span>
          {!ready && <button onClick={() => void init()} className="underline">retry</button>}
          <button onClick={clearError} aria-label="Dismiss" className="text-bad/70 hover:text-bad">
            ✕
          </button>
        </div>
      )}
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(280px,22%)_minmax(0,1fr)_minmax(320px,26%)] lg:grid-rows-[minmax(0,1fr)_minmax(0,38%)]">
        <div className="flex min-h-0 flex-col lg:row-span-1">
          <SearchPanel />
        </div>
        <div className="grid min-h-0 grid-rows-[minmax(380px,1fr)_auto] gap-px bg-line lg:grid-rows-[minmax(0,1fr)_auto]">
          <TwinPanel />
          <ChainView />
        </div>
        <div className="grid min-h-0 gap-px bg-line lg:row-span-2 lg:grid-rows-[minmax(0,0.8fr)_minmax(0,1.4fr)_minmax(0,1fr)]">
          <OperatorPanel />
          <VerdictFeed />
          <ApprovalsInbox />
        </div>
        <div className="min-h-[360px] lg:col-span-2 lg:min-h-0">
          <SynthesisPanel />
        </div>
      </main>
      {dialog === "inject" && <InjectDialog onClose={() => setDialog(null)} />}
      {dialog === "scorecard" && <ScorecardDialog onClose={() => setDialog(null)} />}
      <ExplainDrawer />
    </div>
  );
}
