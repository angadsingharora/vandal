"use client";

import { useState } from "react";
import { cx } from "@/lib/format";
import { loopSteps } from "@/lib/loop";
import { useWarRoom, type View } from "@/lib/store";
import type { OperatorKind } from "@/lib/types";
import { SCENARIOS } from "./SearchPanel";
import { Button } from "./ui";

export const WELCOME_KEY = "vandal.welcomed";

/** True on a first visit (not dismissed in this browser yet), or when the URL asks for it with `?welcome`. */
export function wantsWelcome(): boolean {
  if (typeof window === "undefined") return false;
  if (new URLSearchParams(window.location.search).has("welcome")) return true;
  try {
    return !window.localStorage.getItem(WELCOME_KEY);
  } catch {
    return false;
  }
}

const SIDES: { id: View; name: string; product: string; blurb: string; first: string }[] = [
  {
    id: "blue",
    name: "BLUE",
    product: "Vandal Guard",
    blurb: "Watch the finance agent work the live books while Guard checks every action it takes.",
    first: "Starts at step 1: run operations.",
  },
  {
    id: "red",
    name: "RED",
    product: "Vandal Sandbox",
    blurb: "Attack a clone of the company, find the gap, and build a fix Blue can approve.",
    first: "Starts at step 2: unleash Vandal.",
  },
];

const OPERATORS: { id: OperatorKind; label: string; hint: string }[] = [
  { id: "reference", label: "reference Operator", hint: "Deterministic. The quickest way through the loop." },
  { id: "llm", label: "LLM Operator", hint: "Reads messy documents. Needs a key or playback recordings." },
];

const NOTHING_DONE = { operated: false, attacked: false, diagnosed: false, synthesized: false, submitted: false, applied: false, enforced: false };

function Choice({ on, red, onClick, title, children, className }: { on: boolean; red?: boolean; onClick: () => void; title?: string; children: React.ReactNode; className?: string }) {
  return (
    <button
      role="radio"
      aria-checked={on}
      onClick={onClick}
      title={title}
      className={cx(
        "rounded border text-left text-xs transition-colors",
        on ? (red ? "border-red/70 bg-red/10 text-ink" : "border-blue/70 bg-blue/10 text-ink") : "border-line text-dim hover:border-dim hover:text-ink",
        className,
      )}
    >
      {children}
    </button>
  );
}

/** First-visit landing: what Vandal is, the loop, and three choices that seed the war room. */
export function Welcome({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const [side, setSide] = useState<View>("blue");
  const [scenario, setScenario] = useState(s.search.scenario);
  const [operator, setOperator] = useState<OperatorKind>(s.operator);
  const [entering, setEntering] = useState(false);
  const steps = loopSteps(NOTHING_DONE);

  const enter = async () => {
    setEntering(true);
    try {
      window.localStorage.setItem(WELCOME_KEY, "1");
    } catch {
      /* private mode: show it again next time */
    }
    s.setSearch({ scenario });
    if (operator !== s.operator) await s.reset(s.summary?.policy ?? "v0", operator);
    await s.setView(side);
    setEntering(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-bg/95 p-4 pt-[6vh] backdrop-blur-sm">
      <div role="dialog" aria-modal aria-labelledby="welcome-title" className="w-full max-w-3xl border border-line bg-panel shadow-2xl">
        <header className="border-b border-line px-6 py-5">
          <div className="text-[10px] uppercase tracking-[0.2em] text-faint">Welcome to</div>
          <div className="mt-0.5 flex items-baseline gap-3">
            <h1 id="welcome-title" className="text-2xl font-black tracking-[0.25em] text-ink">
              VANDAL
            </h1>
            <span className="text-xs text-dim">Break it. Fix it. Prove it.</span>
          </div>
          <p className="mt-2 max-w-2xl text-xs leading-relaxed text-dim">
            A finance agent pays the bills. <span className="text-blue">Guard</span> checks every action it takes against the books.{" "}
            <span className="text-red">Vandal</span> attacks a clone until the books break, names the broken link, and builds a control
            that Guard then enforces. Nothing here moves real money.
          </p>
          <ol className="mt-3 flex flex-wrap items-center gap-1" aria-label="The loop">
            {steps.map((st, i) => {
              const red = st.side === "red";
              return (
                <li key={st.n} className="flex items-center gap-1">
                  {i > 0 && <span aria-hidden className={cx("h-px w-3", steps[i - 1].side !== st.side ? "bg-dim" : "bg-line")} />}
                  <span
                    title={st.next}
                    className={cx("flex h-6 items-center gap-1.5 rounded-full border px-2 text-[11px]", red ? "border-red/40 text-red" : "border-blue/40 text-blue")}
                  >
                    <span className={cx("num flex size-4 items-center justify-center rounded-full text-[9px] font-bold text-bg", red ? "bg-red" : "bg-blue")}>
                      {st.n}
                    </span>
                    {st.label}
                  </span>
                </li>
              );
            })}
          </ol>
        </header>

        <div className="space-y-5 px-6 py-5">
          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-faint">Start on</div>
            <div role="radiogroup" aria-label="Side" className="grid gap-2 sm:grid-cols-2">
              {SIDES.map((x) => {
                const red = x.id === "red";
                return (
                  <Choice key={x.id} on={side === x.id} red={red} onClick={() => setSide(x.id)} className={cx("border-l-4 p-3", red ? "border-l-red" : "border-l-blue")}>
                    <div className="flex items-center gap-2">
                      <span className={cx("text-[11px] font-bold tracking-wider", red ? "text-red" : "text-blue")}>{x.name}</span>
                      <span className="font-semibold text-ink">{x.product}</span>
                    </div>
                    <p className="mt-1 leading-snug text-dim">{x.blurb}</p>
                    <p className="mt-1 text-[11px] text-faint">{x.first}</p>
                  </Choice>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 sm:grid-cols-[1fr_auto]">
            <div>
              <div className="mb-2 text-[10px] uppercase tracking-wider text-faint">Threat for Red to search</div>
              <div role="radiogroup" aria-label="Scenario" className="flex flex-col gap-1">
                {SCENARIOS.map((x) => (
                  <Choice key={x.id} on={scenario === x.id} red onClick={() => setScenario(x.id)} title={x.hint} className="flex items-center gap-2 px-2 py-1">
                    <span className={cx("num text-[10px] font-bold uppercase", scenario === x.id ? "text-red" : "text-faint")}>{x.id}</span>
                    {x.label}
                  </Choice>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-2 text-[10px] uppercase tracking-wider text-faint">Finance agent</div>
              <div role="radiogroup" aria-label="Operator" className="flex flex-col gap-1">
                {OPERATORS.map((x) => (
                  <Choice key={x.id} on={operator === x.id} onClick={() => setOperator(x.id)} title={x.hint} className="px-2 py-1">
                    {x.label}
                  </Choice>
                ))}
              </div>
            </div>
          </section>
        </div>

        <footer className="flex flex-wrap items-center gap-3 border-t border-line px-6 py-3">
          <span className="text-[11px] text-faint">All of this can be changed later from the top bar and the panels.</span>
          <div className="ml-auto flex items-center gap-2">
            <Button tone="ghost" onClick={onClose}>
              Skip
            </Button>
            <Button tone={side === "red" ? "red" : "blue"} onClick={enter} busy={entering} disabled={!s.ready}>
              {s.ready ? "Enter the war room" : "Connecting…"}
            </Button>
          </div>
        </footer>
      </div>
    </div>
  );
}
