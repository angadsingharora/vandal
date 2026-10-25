"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { currentStep, loopSteps } from "@/lib/loop";
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

/** Where the demo is: seven steps, coloured by the side that does them. Click one to go there. */
export function LoopStrip() {
  const s = useWarRoom();
  const steps = loopSteps({
    operated: s.operate.phase === "done",
    attacked: !!s.attack,
    diagnosed: s.diagnosis.phase === "done" && !!s.diagnosis.data,
    synthesized: !!s.synth.result?.policy,
    submitted: !!s.patch,
    applied: !!s.appliedPolicy,
    enforced: !!s.replays.after,
  });
  const now = currentStep(steps);

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line bg-bg px-4 py-1.5">
      <ol className="flex flex-wrap items-center gap-1" aria-label="Demo loop">
        {steps.map((st, i) => {
          const red = st.side === "red";
          const current = now?.n === st.n;
          return (
            <li key={st.n} className="flex items-center gap-1">
              {i > 0 && <span aria-hidden className={cx("h-px w-3", steps[i - 1].side !== st.side ? "bg-dim" : "bg-line")} />}
              <button
                onClick={() => void s.setView(st.side)}
                aria-current={current ? "step" : undefined}
                title={`${red ? "Vandal Strike" : "Vandal Guard"}: ${st.next}`}
                className={cx(
                  "flex h-6 items-center gap-1.5 rounded-full border px-2 text-[11px] transition-colors",
                  st.done && (red ? "border-red/40 text-red" : "border-blue/40 text-blue"),
                  current && (red ? "border-red bg-red/20 text-ink" : "border-blue bg-blue/20 text-ink"),
                  !st.done && !current && "border-line text-faint hover:text-dim",
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
              Next{s.view !== now.side && ` (${now.side === "red" ? "Strike" : "Guard"})`}:
            </span>{" "}
            {now.next}
          </>
        ) : (
          <span className="text-ok">Loop closed: Strike found the gap, built and proved a fix, and Guard now holds the attack.</span>
        )}
      </p>
    </div>
  );
}

export function TopBar({ onScorecard, onWelcome }: { onScorecard: () => void; onWelcome: () => void }) {
  const s = useWarRoom();
  const [policy, setPolicy] = useState("v0");
  const [resetting, setResetting] = useState(false);

  const reset = async () => {
    setResetting(true);
    await s.reset(policy);
    setResetting(false);
  };

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-panel px-4 py-2">
      <button onClick={onWelcome} title="Back to the welcome screen" className="flex items-baseline gap-2.5 rounded px-1 -mx-1 hover:bg-raised">
        <span className="text-[15px] font-black tracking-[0.25em] text-ink">VANDAL</span>
      </button>

      <SideSwitch />

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
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
        <span aria-hidden className="mx-1 h-4 w-px bg-line" />
        <Button onClick={onScorecard} disabled={!s.ready}>
          Scorecard
        </Button>
        <Toggle
          label="Playback"
          on={!!s.settings?.playback}
          onChange={(v) => s.setPlayback(v)}
          title="Serve LLM answers only from recorded calls (DEMO_PLAYBACK)"
        />
        <Toggle label="Judge view" on={s.judge} onChange={() => s.toggleJudge()} title="Reveal the oracle's answer key" />
        <span
          className={cx("rounded-sm px-1.5 py-0.5 text-[10px] font-semibold", s.api?.mode === "mock" ? "bg-warn/15 text-warn" : "bg-ok/10 text-ok")}
          title={s.api?.mode === "mock" ? "In-browser mock API, recorded from the real backend" : "Connected to the backend"}
        >
          {s.api?.mode === "mock" ? "MOCK" : "LIVE"}
        </span>
      </div>
    </header>
  );
}
