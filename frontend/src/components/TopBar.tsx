"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { currentStep, loopSteps, STAGES, sideOf } from "@/lib/loop";
import { useWarRoom, type View } from "@/lib/store";
import { Button } from "./ui";

function Toggle({ label, on, onChange, title }: { label: string; on: boolean; onChange: (v: boolean) => void; title: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      title={title}
      onClick={() => onChange(!on)}
      className={cx(
        "flex h-7 items-center gap-1.5 rounded border px-2 text-xs",
        on ? "border-esc/60 bg-esc/15 text-esc" : "border-line text-dim hover:text-ink",
      )}
    >
      <span className={cx("inline-block h-3 w-5 rounded-full p-px transition-colors", on ? "bg-esc" : "bg-line")}>
        <span className={cx("block size-2.5 rounded-full bg-bg transition-transform", on && "translate-x-2")} />
      </span>
      {label}
    </button>
  );
}

const SIDES: { id: View; product: string; blurb: string }[] = [
  { id: "blue", product: "Vandal Guard", blurb: "checks every action the agent takes" },
  { id: "red", product: "Vandal Strike", blurb: "attacks a sandbox clone, finds the gap, builds the fix" },
];

function SideSwitch() {
  const view = useWarRoom((s) => s.view);
  const setView = useWarRoom((s) => s.setView);
  return (
    <div role="tablist" aria-label="Side" className="flex rounded-md border border-line bg-bg p-0.5">
      {SIDES.map((x) => {
        const on = view === x.id;
        const red = x.id === "red";
        return (
          <button
            key={x.id}
            role="tab"
            aria-selected={on}
            onClick={() => void setView(x.id)}
            title={x.blurb}
            className={cx(
              "flex items-center gap-2 rounded px-3 py-1 text-left transition-colors",
              on ? (red ? "bg-red/15 text-red" : "bg-blue/15 text-blue") : "text-dim hover:text-ink",
            )}
          >
            <span className={cx("size-2 rounded-full", red ? "bg-red" : "bg-blue", !on && "opacity-50")} />
            <span className={cx("text-xs font-semibold", on ? "text-ink" : "")}>{x.product}</span>
          </button>
        );
      })}
    </div>
  );
}

/** The stepper: seven steps, coloured by the side that does them. The page being looked at is
 * outlined; the step to do next breathes until it is. Click any step to open its page. */
export function LoopStrip() {
  const s = useWarRoom();
  const steps = loopSteps(s.progress());
  const now = currentStep(steps);

  return (
    <nav aria-label="The loop" className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line bg-bg px-4 py-1.5">
      <ol className="flex flex-wrap items-center gap-1">
        {steps.map((st, i) => {
          const red = st.side === "red";
          const current = now?.id === st.id;
          const viewing = s.stage === st.id;
          return (
            <li key={st.id} className="flex items-center gap-1">
              {i > 0 && <span aria-hidden className={cx("h-px w-3", steps[i - 1].side !== st.side ? "bg-dim" : "bg-line")} />}
              <button
                onClick={() => void s.setStage(st.id)}
                aria-current={viewing ? "page" : undefined}
                title={`${red ? "Vandal Strike" : "Vandal Guard"}: ${st.next}`}
                className={cx(
                  "flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] transition-colors",
                  viewing
                    ? red
                      ? "border-red bg-red/15 text-ink"
                      : "border-blue bg-blue/15 text-ink"
                    : st.done
                      ? red
                        ? "border-red/30 text-red/80 hover:text-red"
                        : "border-blue/30 text-blue/80 hover:text-blue"
                      : current
                        ? red
                          ? "border-red/60 text-ink"
                          : "border-blue/60 text-ink"
                        : "border-line text-faint hover:text-dim",
                  current && !viewing && "nudge",
                  current && !viewing && red && "nudge-red",
                )}
              >
                <span
                  className={cx(
                    "num flex size-4 items-center justify-center rounded-full text-[9px] font-bold",
                    st.done || current ? (red ? "bg-red text-bg" : "bg-blue text-bg") : "bg-line text-dim",
                  )}
                >
                  {st.done ? "✓" : st.n}
                </span>
                {st.label}
              </button>
            </li>
          );
        })}
      </ol>
      <p className="min-w-0 flex-1 truncate text-xs text-dim">
        {now ? (
          <>
            <span className={cx("font-semibold", now.side === "red" ? "text-red" : "text-blue")}>
              Next{s.stage !== now.id && `, on ${now.label}`}:
            </span>{" "}
            {now.next}
          </>
        ) : (
          <span className="text-ok">Loop closed: Strike found the gap, built and proved a fix, and Guard now holds the attack.</span>
        )}
      </p>
    </nav>
  );
}

const PAGE_LABEL: Record<string, string> = {
  operate: "Operate",
  attack: "Attack",
  diagnose: "Diagnose",
  fix: "Fix",
  prove: "Prove",
  approve: "Approve",
  enforce: "Enforce",
};

/** The workspace's navigation: the same seven pages as the loop, as plain tabs grouped by the
 * side that owns them. No numbers, no done marks, no "next": nothing is scripted here. */
export function PageNav() {
  const stage = useWarRoom((s) => s.stage);
  const setStage = useWarRoom((s) => s.setStage);
  const summary = useWarRoom((s) => s.summary);
  const ws = useWarRoom((s) => s.ws);
  return (
    <nav aria-label="Pages" className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line bg-bg px-4 py-1.5">
      {(["blue", "red"] as const).map((side) => (
        <div key={side} className="flex items-center gap-1" role="tablist" aria-label={side === "red" ? "Vandal Strike" : "Vandal Guard"}>
          <span className={cx("mr-1 text-[10px] font-semibold uppercase tracking-wider", side === "red" ? "text-red" : "text-blue")}>
            {side === "red" ? "Strike" : "Guard"}
          </span>
          {STAGES.filter((st) => sideOf(st) === side).map((st) => {
            const on = stage === st;
            return (
              <button
                key={st}
                role="tab"
                aria-selected={on}
                aria-current={on ? "page" : undefined}
                onClick={() => void setStage(st)}
                className={cx(
                  "h-7 rounded-full border px-2.5 text-[11px] transition-colors",
                  on ? (side === "red" ? "border-red bg-red/15 text-ink" : "border-blue bg-blue/15 text-ink") : "border-line text-dim hover:text-ink",
                )}
              >
                {PAGE_LABEL[st]}
              </button>
            );
          })}
        </div>
      ))}
      {summary && (
        <p className="ml-auto min-w-0 truncate text-[11px] text-dim" title="The run being worked on: company, policy, seed">
          <span className="font-semibold text-ink">{summary.company}</span> · <span className="num">{summary.policy}</span> · seed{" "}
          <span className="num">{summary.seed}</span>
          {ws.profile !== summary.profile && <span className="text-warn"> · settings changed: start a new run to apply</span>}
        </p>
      )}
    </nav>
  );
}

export function TopBar({
  onScorecard,
  onWelcome,
  onWorkspace,
}: {
  onScorecard: () => void;
  onWelcome: () => void;
  onWorkspace: () => void;
}) {
  const s = useWarRoom();
  const demo = s.mode === "demo";
  const [policy, setPolicy] = useState("v0");
  const [resetting, setResetting] = useState(false);

  const reset = async () => {
    setResetting(true);
    await (demo ? s.reset(policy) : s.startRun());
    setResetting(false);
  };

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-panel px-4 py-2">
      <button onClick={onWelcome} title="Back to the welcome screen" className="flex items-baseline gap-2.5 rounded px-1 -mx-1 hover:bg-raised">
        <span className="text-[15px] font-black tracking-[0.25em] text-ink">VANDAL</span>
      </button>

      <SideSwitch />

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        {demo ? (
          <>
            <label className="sr-only" htmlFor="policy">Starting policy</label>
            <select
              id="policy"
              value={policy}
              onChange={(e) => setPolicy(e.target.value)}
              className="h-7 rounded border border-line bg-raised px-1.5 text-xs"
              title="Guard's controls for the new run"
            >
              {s.policies.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
            <Button onClick={reset} busy={resetting} title="Drop every run and seed the company again">
              Reset demo
            </Button>
          </>
        ) : (
          <>
            <Button onClick={onWorkspace} title="Company, run, and how each job is asked for">
              Settings
            </Button>
            <Button onClick={reset} busy={resetting} disabled={!s.ready} title="Start over on a run seeded from the workspace's company and policy">
              New run
            </Button>
          </>
        )}
        <span aria-hidden className="mx-1 h-4 w-px bg-line" />
        <Button onClick={onScorecard} disabled={!s.ready}>
          Scorecard
        </Button>
        <Toggle
          label="Playback"
          on={!!s.settings?.playback}
          onChange={(v) => s.setPlayback(v)}
          title={demo ? "Serve LLM answers only from recorded calls (DEMO_PLAYBACK)" : "Serve model calls and recorded jobs from the cache instead of computing"}
        />
        {demo && <Toggle label="Judge view" on={s.judge} onChange={() => s.toggleJudge()} title="Reveal the oracle's answer key" />}
        {s.api?.mode === "mock" ? (
          <a
            href="/"
            className={cx("rounded-sm bg-warn/15 px-1.5 py-0.5 text-[10px] font-semibold text-warn hover:bg-warn/25")}
            title="The loop from a recording of the real backend, replayed in the browser. Click for the live backend."
          >
            RECORDED
          </a>
        ) : (
          <span className={cx("rounded-sm bg-ok/10 px-1.5 py-0.5 text-[10px] font-semibold text-ok")} title="Connected to the backend">
            LIVE
          </span>
        )}
      </div>
    </header>
  );
}
