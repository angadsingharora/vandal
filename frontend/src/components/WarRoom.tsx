"use client";

import { useEffect, useState, type ReactNode } from "react";
import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { AttackVerdict } from "./AttackVerdict";
import { ApprovalsInbox, EnforcedPolicy, OperatorPanel, RunOperations, VerdictFeed } from "./BluePanels";
import { ChainView } from "./ChainView";
import { ExplainDrawer } from "./ExplainDrawer";
import { HuntPanel } from "./HuntPanel";
import { InjectDialog } from "./InjectDialog";
import { ScorecardDialog } from "./ScorecardDialog";
import { SearchPanel } from "./SearchPanel";
import { SynthesisPanel } from "./SynthesisPanel";
import { LoopStrip, TopBar } from "./TopBar";
import { TwinPanel } from "./TwinPanel";
import { Button, LiveDot } from "./ui";

/** The runs a side can look at: Blue watches Live (and a replay it asked for), Red its sandbox clones. */
function RunTabs() {
  const s = useWarRoom();
  if (s.tabs.length < 2) return null;
  return (
    <nav aria-label="Runs" className="flex min-w-0 items-center gap-1 overflow-x-auto">
      <span className="text-[10px] uppercase tracking-wider text-faint">Watching</span>
      {s.tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => s.focus(t.id)}
          title={t.id}
          className={cx(
            "flex h-6 shrink-0 items-center gap-1.5 rounded border px-2 text-[11px]",
            s.focusRunId === t.id ? "border-ink/40 bg-raised text-ink" : "border-line text-dim hover:text-ink",
          )}
        >
          {t.kind === "live" && <LiveDot className="text-ok" />}
          {t.kind === "live" ? `Live · ${t.policy}` : t.label}
        </button>
      ))}
    </nav>
  );
}

/** One line under the strip that says what this side is and holds its main controls. */
function Banner({ side, title, children, actions }: { side: "red" | "blue"; title: string; children: ReactNode; actions?: ReactNode }) {
  const red = side === "red";
  return (
    <div
      className={cx(
        "flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-l-4 px-4 py-2",
        red ? "border-b-red/30 border-l-red bg-red/[0.06]" : "border-b-blue/30 border-l-blue bg-blue/[0.06]",
      )}
    >
      <div className="min-w-0 max-w-3xl flex-1 basis-80">
        <div className={cx("text-xs font-bold tracking-wider", red ? "text-red" : "text-blue")}>{title}</div>
        <p className="text-xs leading-snug text-dim">{children}</p>
      </div>
      <RunTabs />
      <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>
    </div>
  );
}

function BlueView() {
  const s = useWarRoom();
  return (
    <>
      <Banner side="blue" title="BLUE · VANDAL GUARD — the live path" actions={<RunOperations />}>
        The <span className="text-ink">Operator</span> is the finance agent doing {s.summary?.company ?? "the company"}&apos;s payables.
        Guard sits between it and the money: every tool call is checked against an independent source of truth and allowed, held,
        or escalated to a human. Fixes from Red land in the approvals inbox.
      </Banner>
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(300px,26%)_minmax(0,1fr)_minmax(340px,28%)] lg:grid-rows-[minmax(0,1fr)_minmax(0,40%)]">
        <div className="flex min-h-0 min-w-0 flex-col lg:row-span-2">
          <OperatorPanel />
        </div>
        <div className="flex min-h-0 min-w-0 flex-col">
          <VerdictFeed />
        </div>
        <div className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-px bg-line lg:row-span-2">
          <EnforcedPolicy />
          <ApprovalsInbox />
        </div>
        <div className="flex min-h-[320px] min-w-0 flex-col lg:min-h-0">
          <TwinPanel title="Books" />
        </div>
      </main>
    </>
  );
}

function RedView({ onInject }: { onInject: () => void }) {
  const s = useWarRoom();
  const focused = s.tabs.find((t) => t.id === s.focusRunId);
  return (
    <>
      <Banner
        side="red"
        title="RED · VANDAL SANDBOX — a clone, never the live books"
        actions={
          <Button tone="red" onClick={onInject} disabled={!s.ready}>
            Try your own scenario
          </Button>
        }
      >
        Vandal clones the company into a deterministic financial twin and attacks it under{" "}
        <span className="num text-ink">{s.summary?.policy ?? focused?.policy ?? "v0"}</span>: it searches for events that break the
        books, names the broken link, then builds and proves a control. Nothing here moves real money; the fix only reaches Guard
        once a human approves it.
      </Banner>
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(300px,24%)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)_minmax(0,38%)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-px overflow-y-auto bg-line lg:row-span-2">
          <SearchPanel />
          <HuntPanel />
        </div>
        {/* The twin keeps at least a few table rows on screen; a tall chain (diagnosis open) scrolls instead. */}
        <div className="flex min-h-0 min-w-0 flex-col gap-px overflow-y-auto bg-line">
          <AttackVerdict />
          <div className="flex min-h-[380px] flex-1 flex-col lg:min-h-[280px]">
            <TwinPanel title="Sandbox twin" />
          </div>
          <div className="shrink-0">
            <ChainView />
          </div>
        </div>
        <div className="min-h-[360px] min-w-0 lg:min-h-0">
          <SynthesisPanel />
        </div>
      </main>
    </>
  );
}

/** DESIGN §14, split by side: Blue (Guard) watches the Operator in the live path; Red (Sandbox)
 * attacks a clone, diagnoses, and synthesizes a fix that Blue approves and enforces. */
export function WarRoom() {
  const init = useWarRoom((s) => s.init);
  const error = useWarRoom((s) => s.error);
  const clearError = useWarRoom((s) => s.clearError);
  const ready = useWarRoom((s) => s.ready);
  const view = useWarRoom((s) => s.view);
  const [dialog, setDialog] = useState<"inject" | "scorecard" | null>(null);

  useEffect(() => {
    void init();
  }, [init]);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      <TopBar onScorecard={() => setDialog("scorecard")} />
      <LoopStrip />
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
      {view === "blue" ? <BlueView /> : <RedView onInject={() => setDialog("inject")} />}
      {dialog === "inject" && <InjectDialog onClose={() => setDialog(null)} />}
      {dialog === "scorecard" && <ScorecardDialog onClose={() => setDialog(null)} />}
      <ExplainDrawer />
    </div>
  );
}
