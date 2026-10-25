"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { currentStep, loopSteps } from "@/lib/loop";
import { useWarRoom } from "@/lib/store";
import { Button } from "./ui";

function Toggle({ label, on, onChange, title }: { label: string; on: boolean; onChange: (v: boolean) => void; title: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      title={title}
      onClick={() => onChange(!on)}
      className={cx("flex h-7 items-center gap-1.5 px-1.5 text-[12px]", on ? "text-ink" : "text-dim hover:text-ink")}
    >
      <span className={cx("inline-block h-3.5 w-6 rounded-full p-px transition-colors", on ? "bg-ink" : "bg-line")}>
        <span className={cx("block size-3 rounded-full bg-bg transition-transform", on && "translate-x-2.5")} />
      </span>
      {label}
    </button>
  );
}

/** The loop's state, read once for the gutter and the page heads. */
export function useLoop() {
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
  return { steps, now: currentStep(steps) };
}

export function TopBar({ onScorecard }: { onScorecard: () => void }) {
  const s = useWarRoom();
  const [policy, setPolicy] = useState("v0");
  const [resetting, setResetting] = useState(false);

  const reset = async () => {
    setResetting(true);
    await s.reset(policy, s.operator);
    setResetting(false);
  };

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-bg px-4 py-2">
      <span className="text-[15px] font-semibold leading-none tracking-tight text-ink">Vandal</span>
      <span className="text-[12px] text-dim">{s.summary?.company ?? "the company"}</span>

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        <label className="sr-only" htmlFor="policy">
          Starting policy
        </label>
        <select
          id="policy"
          value={policy}
          onChange={(e) => setPolicy(e.target.value)}
          className="num h-7 rounded border border-ink/20 bg-bg px-1.5 text-[12px] text-ink"
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
        <Button onClick={onScorecard} disabled={!s.ready}>
          Scorecard
        </Button>
        <span aria-hidden className="mx-1.5 h-4 w-px bg-line" />
        <Toggle label="Playback" on={!!s.settings?.playback} onChange={(v) => s.setPlayback(v)} title="Serve LLM answers only from recorded calls (DEMO_PLAYBACK)" />
        <Toggle label="Judge view" on={s.judge} onChange={() => s.toggleJudge()} title="Reveal the oracle's answer key" />
        <span
          className={cx("ml-1 text-[11px] font-medium", s.api?.mode === "mock" ? "text-warn" : "text-blue")}
          title={s.api?.mode === "mock" ? "In-browser mock API, recorded from the real backend" : "Connected to the backend"}
        >
          {s.api?.mode === "mock" ? "Mock" : "Live"}
        </span>
      </div>
    </header>
  );
}
