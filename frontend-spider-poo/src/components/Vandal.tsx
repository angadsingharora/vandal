"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { Chip } from "./bits";
import { Console } from "./Console";
import { Crawl } from "./Crawl";
import { Weave } from "./Weave";
import { Web } from "./Web";

type Screen = "web" | "crawl" | "weave";

const SCREENS: { id: Screen; n: string; title: string; who: string; tone: "red" | "amber" | "blue"; blurb: string }[] = [
  { id: "web", n: "01", title: "The Web", who: "Red crawls", tone: "red", blurb: "Thread by thread, outward from the company, until it finds the tear where money falls through." },
  { id: "crawl", n: "02", title: "The Crawl", who: "The Operator reads", tone: "amber", blurb: "A crawler walks a messy document line by line and pulls each field out on a thread." },
  { id: "weave", n: "03", title: "The Weave", who: "Blue mends", tone: "blue", blurb: "Each candidate control is a thread across the tear. The spider crawls again. What holds is tied to six anchors." },
];

/** The skeleton shell: three pictures on the left, the plain record on the right. */
export function Vandal() {
  const [screen, setScreen] = useState<Screen>("web");
  const [torn, setTorn] = useState(false);
  const [judge, setJudge] = useState(false);
  const [playback, setPlayback] = useState(true);
  const cur = SCREENS.find((s) => s.id === screen)!;

  return (
    <div className="flex min-h-screen flex-col lg:h-screen lg:overflow-hidden">
      <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-bg2/80 px-5 py-2.5 backdrop-blur">
        <div className="flex items-baseline gap-3">
          <span className="display text-[17px] font-bold tracking-[0.3em] text-red">VANDAL</span>
          <span className="hidden text-[11px] text-dim xl:inline">The spider is Red. The web is Blue.</span>
        </div>
        <nav aria-label="Screens" className="flex items-center gap-1 rounded-xl border border-line bg-panel p-1">
          {SCREENS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setScreen(s.id)}
              aria-current={screen === s.id ? "page" : undefined}
              className={cx(
                "flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors",
                screen === s.id ? "bg-raised text-ink" : "text-dim hover:text-ink",
              )}
            >
              <span className={cx("num text-[10px]", s.tone === "red" ? "text-red" : s.tone === "amber" ? "text-amber" : "text-blue")}>{s.n}</span>
              {s.title}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-2 text-xs">
          <select aria-label="Policy" className="h-8 rounded-lg border border-line bg-panel px-2 text-xs text-ink" defaultValue="v0">
            <option>v0</option>
            <option>v1</option>
            <option>v1-synth</option>
          </select>
          <button type="button" className="h-8 rounded-lg border border-line bg-panel px-3 text-xs text-ink hover:border-dim">Reset demo</button>
          <button type="button" className="h-8 rounded-lg bg-blue px-3 text-xs font-semibold text-[#021018] glow-blue">Run operations</button>
          <span className="num rounded-lg border border-line px-2 py-1 text-[11px] text-dim">Live · v0 · day 5</span>
          {torn && <span className="num rounded-lg border border-red/50 bg-red/10 px-2 py-1 text-[11px] text-red2">Attack · v0 · $40,000 torn</span>}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Toggle label="Playback" on={playback} onChange={setPlayback} title="Serve LLM answers only from recorded calls" />
          <Toggle label="Judge view" on={judge} onChange={setJudge} title="Reveal the oracle's answer key" />
          <Chip tone="ok">LIVE</Chip>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          <div className="rise flex flex-wrap items-end gap-x-4 gap-y-1 px-1">
            <h1 className="display text-2xl font-semibold text-ink">
              <span className={cx("num mr-2 text-base", cur.tone === "red" ? "text-red" : cur.tone === "amber" ? "text-amber" : "text-blue")}>{cur.n}</span>
              {cur.title}
            </h1>
            <Chip tone={cur.tone}>{cur.who}</Chip>
            <p className="text-[12.5px] text-dim">{cur.blurb}</p>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {screen === "web" && <Web judge={judge} onTear={() => setTorn(true)} />}
            {screen === "crawl" && <Crawl judge={judge} />}
            {screen === "weave" && <Weave />}
          </div>
        </div>
        <div className="min-h-[420px] lg:min-h-0">
          <Console attacked={torn} />
        </div>
      </main>
    </div>
  );
}

function Toggle({ label, on, onChange, title }: { label: string; on: boolean; onChange: (v: boolean) => void; title: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      title={title}
      onClick={() => onChange(!on)}
      className={cx(
        "flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs",
        on ? "border-esc/60 bg-esc/15 text-esc" : "border-line text-dim hover:text-ink",
      )}
    >
      <span className={cx("inline-block h-3.5 w-6 rounded-full p-px transition-colors", on ? "bg-esc" : "bg-line2")}>
        <span className={cx("block size-3 rounded-full bg-bg transition-transform", on && "translate-x-2.5")} />
      </span>
      {label}
    </button>
  );
}
