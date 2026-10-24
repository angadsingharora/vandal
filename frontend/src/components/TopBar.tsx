"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { Button, LiveDot } from "./ui";

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

export function TopBar({ onInject, onScorecard }: { onInject: () => void; onScorecard: () => void }) {
  const s = useWarRoom();
  const [policy, setPolicy] = useState("v0");
  const [days, setDays] = useState(5);
  const [resetting, setResetting] = useState(false);
  const operating = s.operate.phase === "running";

  const reset = async () => {
    setResetting(true);
    await s.reset(policy);
    setResetting(false);
  };

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-panel px-4 py-2">
      <div className="flex items-baseline gap-2.5">
        <span className="text-[15px] font-black tracking-[0.25em] text-red">VANDAL</span>
        <span className="hidden text-[11px] text-dim xl:inline">Break it. Fix it. Prove it.</span>
      </div>

      <div className="flex items-center gap-1.5">
        <label className="sr-only" htmlFor="policy">Policy</label>
        <select
          id="policy"
          value={policy}
          onChange={(e) => setPolicy(e.target.value)}
          className="h-7 rounded border border-line bg-raised px-1.5 text-xs"
          title="Blue's controls for a new run"
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
      </div>

      <div className="flex items-center gap-1.5">
        <label className="sr-only" htmlFor="days">Business days</label>
        <input
          id="days"
          type="number"
          min={1}
          max={30}
          value={days}
          onChange={(e) => setDays(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
          className="num h-7 w-12 rounded border border-line bg-raised px-1.5 text-xs"
          title="Business days to operate"
        />
        <Button tone="blue" onClick={() => s.operateDays(days)} busy={operating} disabled={!s.ready}>
          Run operations
        </Button>
        {operating && s.operate.day != null && (
          <span className="num text-[11px] text-dim">
            day {s.operate.day} · {s.operate.events} events
          </span>
        )}
      </div>

      <nav aria-label="Runs" className="flex min-w-0 items-center gap-1 overflow-x-auto">
        {s.tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => s.focus(t.id)}
            title={t.id}
            className={cx(
              "flex h-7 shrink-0 items-center gap-1.5 rounded border px-2 text-xs",
              s.focusRunId === t.id ? "border-blue/60 bg-blue/10 text-ink" : "border-line text-dim hover:text-ink",
            )}
          >
            {t.kind === "live" && <LiveDot className="text-ok" />}
            {t.label}
            <span className="text-faint">{t.kind === "live" ? t.policy : ""}</span>
          </button>
        ))}
      </nav>

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        <Button tone="red" onClick={onInject} disabled={!s.ready}>
          Try your own scenario
        </Button>
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
