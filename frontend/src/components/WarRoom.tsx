"use client";

import { useEffect, useState } from "react";
import { useWarRoom } from "@/lib/store";
import { ApprovePage } from "./ApprovePage";
import { AttackPage } from "./AttackPage";
import { DiagnosePage } from "./DiagnosePage";
import { EnforcePage } from "./EnforcePage";
import { ExplainDrawer } from "./ExplainDrawer";
import { FixPage } from "./FixPage";
import { InjectDialog } from "./InjectDialog";
import { OperatePage } from "./OperatePage";
import { ProvePage } from "./ProvePage";
import { ScorecardDialog } from "./ScorecardDialog";
import { LoopStrip, TopBar } from "./TopBar";
import { wantsWelcome, Welcome } from "./Welcome";

/** DESIGN §14 as seven pages, one per step of the loop. Blue (Guard) operates, approves and
 * enforces; Red (Strike) attacks a clone, diagnoses, fixes and proves. The stepper under the
 * top bar moves between them, and each page's footer carries the loop forward. */
export function WarRoom() {
  const init = useWarRoom((s) => s.init);
  const error = useWarRoom((s) => s.error);
  const clearError = useWarRoom((s) => s.clearError);
  const ready = useWarRoom((s) => s.ready);
  const waking = useWarRoom((s) => s.waking);
  const stage = useWarRoom((s) => s.stage);
  const [dialog, setDialog] = useState<"inject" | "scorecard" | null>(null);
  const [welcome, setWelcome] = useState(false);

  useEffect(() => {
    void init();
    setWelcome(wantsWelcome()); // after mount, so the server and first client render agree
  }, [init]);

  const page = {
    operate: <OperatePage />,
    attack: <AttackPage onInject={() => setDialog("inject")} />,
    diagnose: <DiagnosePage />,
    fix: <FixPage />,
    prove: <ProvePage />,
    approve: <ApprovePage />,
    enforce: <EnforcePage />,
  }[stage];

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      <TopBar onScorecard={() => setDialog("scorecard")} onWelcome={() => setWelcome(true)} />
      <LoopStrip />
      {error && (
        <div role="alert" className="flex items-center gap-3 border-b border-bad/40 bg-bad/10 px-4 py-1.5 text-xs text-bad">
          <span className="font-semibold">Error</span>
          <span className="min-w-0 flex-1 truncate">{error}</span>
          {!ready && (
            <button onClick={() => void init()} className="underline">
              retry
            </button>
          )}
          <button onClick={clearError} aria-label="Dismiss" className="text-bad/70 hover:text-bad">
            ✕
          </button>
        </div>
      )}
      {waking && !ready && !error && (
        <div role="status" className="flex items-center gap-3 border-b border-warn/40 bg-warn/10 px-4 py-1.5 text-xs text-warn">
          <span className="font-semibold">Waking the API</span>
          <span className="min-w-0 flex-1 truncate">
            The demo host sleeps after fifteen idle minutes and takes about a minute to wake. Nothing is wrong.
          </span>
        </div>
      )}
      {page}
      {dialog === "inject" && <InjectDialog onClose={() => setDialog(null)} />}
      {dialog === "scorecard" && <ScorecardDialog onClose={() => setDialog(null)} />}
      {welcome && <Welcome onClose={() => setWelcome(false)} />}
      <ExplainDrawer />
    </div>
  );
}
