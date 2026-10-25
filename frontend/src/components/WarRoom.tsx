"use client";

import { useEffect, useState, type ReactNode } from "react";
import { cx, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { ApprovalsInbox, EnforcedPolicy, OperatorPanel, RunOperations, VerdictFeed } from "./BluePanels";
import { ChainView } from "./ChainView";
import { EvidenceScan } from "./EvidenceScan";
import { ExplainDrawer } from "./ExplainDrawer";
import { InjectDialog } from "./InjectDialog";
import { ScorecardDialog } from "./ScorecardDialog";
import { BreakAndRule } from "./BreakAndRule";
import { SystemMap } from "./SystemMap";
import { SynthesisPanel } from "./SynthesisPanel";
import { ExchangeBand } from "./ExchangeBand";
import { TopBar, useLoop } from "./TopBar";
import { TwinPanel } from "./TwinPanel";
import { wantsWelcome, Welcome } from "./Welcome";
import { Button, LiveDot, Verdict } from "./ui";

/** The runs a side can look at: Blue watches Live (and a replay it asked for), Red its sandbox clones. */
function RunTabs() {
  const s = useWarRoom();
  if (s.tabs.length < 2) return null;
  return (
    <nav aria-label="Runs" className="flex min-w-0 items-center gap-3 overflow-x-auto">
      {s.tabs.map((t) => {
        const on = s.focusRunId === t.id;
        return (
          <button
            key={t.id}
            onClick={() => s.focus(t.id)}
            title={t.id}
            className={cx("num flex h-6 shrink-0 items-center gap-1.5 border-b-2 text-[11.5px]", on ? "border-ink text-ink" : "border-transparent text-dim hover:text-ink")}
          >
            {t.kind === "live" && <LiveDot className="text-blue" />}
            {t.kind === "live" ? `Live ${t.policy}` : t.label.replace(" · ", " ")}
          </button>
        );
      })}
    </nav>
  );
}

/** The head of a page: who works here, one line on what this is, and what to click next. */
function PageHead({ side, title, children, actions }: { side: "red" | "blue"; title: string; children: ReactNode; actions?: ReactNode }) {
  const red = side === "red";
  const { now } = useLoop();
  const mine = now?.side === side;
  return (
    <div className="shrink-0 border-b border-line px-4 pb-2.5 pt-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className={cx("text-[18px] font-semibold leading-none tracking-tight", red ? "text-red" : "text-blue")}>{title}</h1>
        <p className="min-w-0 flex-1 basis-64 text-[12px] text-dim">{children}</p>
        <RunTabs />
        <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>
      </div>
      <p className={cx("mt-2 text-[12.5px]", mine ? (red ? "text-red" : "text-blue") : "text-dim")}>
        {now ? (
          mine ? (
            <>
              <span className="font-semibold">Next</span> {now.next}
            </>
          ) : (
            <>
              <span className="font-medium">Next, on {now.side === "red" ? "Red" : "Blue"}</span> {now.next}
            </>
          )
        ) : (
          <>Loop closed. Red found the gap, built and proved a fix, and Guard now holds the attack.</>
        )}
      </p>
    </div>
  );
}

function BluePage() {
  return (
    <section className="flex min-h-0 min-w-0 flex-col border-t-2 border-blue bg-bg">
      <PageHead side="blue" title="Guard" actions={<RunOperations />}>
        The live books. Guard checks every action the Operator takes before money moves.
      </PageHead>
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(240px,24%)_minmax(0,1fr)_minmax(300px,28%)] lg:grid-rows-[minmax(0,1fr)_minmax(0,46%)]">
        <div className="flex min-h-0 min-w-0 flex-col">
          <OperatorPanel />
        </div>
        <div className="flex min-h-0 min-w-0 flex-col">
          <VerdictFeed />
        </div>
        <div className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)] gap-px bg-line lg:row-span-2">
          <EnforcedPolicy />
          <ApprovalsInbox />
        </div>
        <div className="flex min-h-[320px] min-w-0 flex-col lg:col-span-2 lg:min-h-0">
          <TwinPanel title="Books" />
        </div>
      </main>
    </section>
  );
}

function RedPage({ onInject }: { onInject: () => void }) {
  const s = useWarRoom();
  const focused = s.tabs.find((t) => t.id === s.focusRunId);
  return (
    <section className="flex min-h-0 min-w-0 flex-col border-t-2 border-red bg-bg">
      <PageHead side="red" title="Sandbox">
        A copy of the books under <span className="num text-ink">{s.summary?.policy ?? focused?.policy ?? "v0"}</span>. Vandal attacks it, names the broken
        link, then builds and proves a fix.
      </PageHead>
      <BreakAndRule onInject={onInject} />
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(0,1fr)_minmax(300px,38%)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-px overflow-y-auto bg-line">
          <SystemMap />
          <EvidenceScan />
          <div className="shrink-0">
            <ChainView />
          </div>
          <div className="flex min-h-[320px] flex-1 flex-col lg:min-h-[240px]">
            <TwinPanel title="Copy of the books" />
          </div>
        </div>
        <div className="min-h-[320px] min-w-0 lg:min-h-0">
          <SynthesisPanel />
        </div>
      </main>
    </section>
  );
}

function MarginRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-line px-3 py-2.5">
      <div className="text-[11px] text-dim">{label}</div>
      <div className="mt-0.5 text-[12.5px] leading-snug text-ink">{children}</div>
    </div>
  );
}

function MarginHead({ side, title, children }: { side: "red" | "blue"; title: string; children: ReactNode }) {
  const red = side === "red";
  const setView = useWarRoom((s) => s.setView);
  const { now } = useLoop();
  const mine = now?.side === side;
  return (
    <div className="shrink-0 border-b border-line px-3 pb-3 pt-3">
      <button onClick={() => void setView(side)} className="text-left">
        <div className={cx("text-[16px] font-semibold leading-none tracking-tight", red ? "text-red" : "text-blue")}>{title}</div>
        <div className="mt-1 text-[11.5px] text-dim">{children}</div>
      </button>
      {mine && now && (
        <div className="mt-3 space-y-2">
          <p className={cx("text-[12px] leading-snug", red ? "text-red" : "text-blue")}>
            <span className="font-semibold">Next</span> {now.next}
          </p>
          <Button tone={side} onClick={() => void setView(side)} className="w-full justify-center">
            Open {red ? "Sandbox" : "Guard"}
          </Button>
        </div>
      )}
    </div>
  );
}

/** Red's page, folded back: what Vandal has found so far. */
function RedMargin() {
  const s = useWarRoom();
  const d = s.diagnosis.data;
  const chosen = s.synth.result?.chosen ?? [];
  const checks = s.verify.checks;
  const passed = checks.filter((c) => c.passed).length;
  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto border-t-2 border-red bg-bg">
      <MarginHead side="red" title="Sandbox">
        A copy of the books. Vandal attacks it and builds the fix.
      </MarginHead>
      <MarginRow label="Found">
        {s.search.phase === "running" ? (
          <span className="num text-dim">
            searching, {s.search.explored.toLocaleString()} sequences <LiveDot className="text-red" />
          </span>
        ) : s.attack ? (
          <>
            <span className="num font-semibold text-red">{usd(s.attack.finding.exposure)}</span> misdirected
            <div className="num text-[11px] text-dim">
              {s.attack.finding.moves.length} moves under {s.attack.policy}
            </div>
          </>
        ) : (
          <span className="text-dim">nothing yet</span>
        )}
      </MarginRow>
      <MarginRow label="Broken link">
        {d ? (
          <>
            <span className="text-red">{d.gap}</span> at {d.link}
          </>
        ) : (
          <span className="text-dim">not diagnosed</span>
        )}
      </MarginRow>
      <MarginRow label="Fix">
        {chosen.length ? (
          <>
            <ul className="num text-[12px]">
              {chosen.map((c) => (
                <li key={c} className="truncate" title={c}>
                  {c.replace(/\(.*\)$/, "")}
                </li>
              ))}
            </ul>
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-dim">
              {checks.length ? (
                <span className="num">
                  {passed} of {checks.length} checks passed
                </span>
              ) : (
                <span>not verified</span>
              )}
              {s.verify.pack && (
                <Verdict tone={s.verify.pack.approvable ? "blue" : "red"}>{s.verify.pack.approvable ? "approvable" : "not approvable"}</Verdict>
              )}
            </div>
          </>
        ) : s.synth.phase === "running" ? (
          <span className="num text-dim">
            {s.synth.log.length} candidates tried <LiveDot className="text-red" />
          </span>
        ) : (
          <span className="text-dim">none yet</span>
        )}
      </MarginRow>
    </aside>
  );
}

/** Blue's page, folded back: what Guard is enforcing and what waits on a human. */
function BlueMargin() {
  const s = useWarRoom();
  const chosen = s.synth.result?.chosen ?? [];
  const live = s.tabs.find((t) => t.kind === "live");
  const version = s.appliedPolicy ?? live?.policy ?? "v0";
  const info = s.policies.find((p) => p.name === version);
  const waiting = s.approvals.payments.length;
  const patch = s.patch;
  const { before, after } = s.replays;
  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto border-t-2 border-blue bg-bg">
      <MarginHead side="blue" title="Guard">
        The live books. Guard checks every action before money moves.
      </MarginHead>
      <MarginRow label="The rule Vandal wrote">
        {chosen.length ? (
          <>
            <ul className="num space-y-1 text-[11.5px] leading-snug text-blue">
              {chosen.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <div className="mt-1 flex items-center gap-2">
              {patch ? (
                <Verdict tone={patch.status === "applied" || patch.status === "approved" ? "blue" : patch.status === "denied" ? "red" : "warn"}>
                  {patch.status}
                </Verdict>
              ) : (
                <span className="text-[11px] text-dim">proven, not yet sent</span>
              )}
            </div>
          </>
        ) : (
          <span className="text-dim">nothing yet — Vandal is still working</span>
        )}
      </MarginRow>
      <MarginRow label="Policy">
        <span className="num font-semibold">{version}</span>
        <span className="text-dim">{info?.controls.length ? `, ${info.controls.length} controls` : ", no extra controls"}</span>
        {s.operate.phase === "running" && (
          <div className="num text-[11px] text-dim">
            operating, day {s.operate.day ?? 0} <LiveDot className="text-blue" />
          </div>
        )}
      </MarginRow>
      <MarginRow label="Inbox">
        {patch && (
          <div className="flex items-center gap-2">
            <span className="num">{patch.version}</span>
            <Verdict tone={patch.status === "applied" || patch.status === "approved" ? "blue" : patch.status === "denied" ? "red" : "warn"}>{patch.status}</Verdict>
          </div>
        )}
        {waiting > 0 && <div className="num">{waiting} payments waiting</div>}
        {!patch && waiting === 0 && <span className="text-dim">nothing waiting</span>}
      </MarginRow>
      <MarginRow label="Red's attack, replayed">
        {before || after ? (
          <div className="space-y-1">
            {[before, after].map(
              (r, i) =>
                r && (
                  <div key={i} className="flex items-center gap-2">
                    <span className="num w-16 text-[11px] text-dim">{r.run.policy}</span>
                    <Verdict tone={r.result.violations.length ? "red" : "blue"} land={i === 1}>
                      {r.result.violations.length ? "broken" : "held"}
                    </Verdict>
                    <span className="num">{usd(r.result.exposure, { cents: false })}</span>
                  </div>
                ),
            )}
          </div>
        ) : (
          <span className="text-dim">not yet</span>
        )}
      </MarginRow>
    </aside>
  );
}

/** Two pages and a gutter: Red's sandbox on the left, Blue's live books on the right, the loop
 * stitched between them. The focused page is wide; the other folds back to a margin. */
export function WarRoom() {
  const init = useWarRoom((s) => s.init);
  const error = useWarRoom((s) => s.error);
  const clearError = useWarRoom((s) => s.clearError);
  const ready = useWarRoom((s) => s.ready);
  const view = useWarRoom((s) => s.view);
  const [dialog, setDialog] = useState<"inject" | "scorecard" | null>(null);
  const [welcome, setWelcome] = useState(false);

  useEffect(() => {
    void init();
    setWelcome(wantsWelcome()); // after mount, so the server and first client render agree
  }, [init]);

  const red = view === "red";

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      {/* the exchange band at the bottom is this layout's loop strip */}
      <TopBar onScorecard={() => setDialog("scorecard")} onWelcome={() => setWelcome(true)} />
      {error && (
        <div role="alert" className="flex items-center gap-3 border-b border-line bg-raised px-4 py-1.5 text-[12px] text-red">
          <span className="font-semibold">Error</span>
          <span className="min-w-0 flex-1 truncate">{error}</span>
          {!ready && (
            <button onClick={() => void init()} className="underline">
              retry
            </button>
          )}
          <button onClick={clearError} aria-label="Dismiss" className="text-red/70 hover:text-red">
            ✕
          </button>
        </div>
      )}
      <div className={cx("grid min-h-0 flex-1 grid-cols-1 gap-px bg-line", red ? "lg:grid-cols-[minmax(0,1fr)_260px]" : "lg:grid-cols-[260px_minmax(0,1fr)]")}>
        <div className={cx("flex min-h-0 min-w-0 flex-col", !red && "max-lg:order-last")}>
          {red ? <RedPage onInject={() => setDialog("inject")} /> : <RedMargin />}
        </div>
        <div className={cx("flex min-h-0 min-w-0 flex-col", red && "max-lg:order-last")}>{red ? <BlueMargin /> : <BluePage />}</div>
      </div>
      <ExchangeBand />
      {dialog === "inject" && <InjectDialog onClose={() => setDialog(null)} />}
      {dialog === "scorecard" && <ScorecardDialog onClose={() => setDialog(null)} />}
      {welcome && <Welcome onClose={() => setWelcome(false)} />}
      <ExplainDrawer />
    </div>
  );
}
