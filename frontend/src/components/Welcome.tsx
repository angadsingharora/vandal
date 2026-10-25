"use client";

import { useEffect, useState } from "react";
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
  const [leaving, setLeaving] = useState(false);
  const steps = loopSteps(NOTHING_DONE);

  // Fade out, then unmount. The card's leave animation is 200ms; the backdrop's 220ms.
  const dismiss = () => setLeaving(true);
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onClose, 230);
    return () => clearTimeout(t);
  }, [leaving, onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dismiss();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    dismiss();
  };

  return (
    <div className={cx("fixed inset-0 z-50 overflow-auto bg-bg", leaving ? "welcome-leave" : "welcome-enter")}>
      {/* Backdrop: a faint grid with one glow per side. */}
      <div aria-hidden className="welcome-grid pointer-events-none absolute inset-0" />
      <div aria-hidden className="pointer-events-none absolute -left-40 -top-40 size-[34rem] rounded-full bg-blue/15 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-40 -right-40 size-[34rem] rounded-full bg-red/15 blur-3xl" />

      <div
        role="dialog"
        aria-modal
        aria-labelledby="welcome-title"
        className="welcome-card relative mx-auto grid min-h-full w-full max-w-7xl gap-10 px-6 py-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(380px,0.9fr)] lg:items-center lg:px-12"
      >
        {/* Left: what this is. */}
        <section className="flex flex-col justify-center">
          <div className="text-xs uppercase tracking-[0.3em] text-faint">Welcome to</div>
          <h1 id="welcome-title" className="mt-2 text-6xl font-black leading-none tracking-[0.2em] text-ink sm:text-7xl lg:text-8xl">
            VANDAL
          </h1>
          <p className="mt-4 text-base font-medium text-dim sm:text-lg">
            Break it. <span className="text-ink">Fix it.</span> Prove it.
          </p>
          <p className="mt-6 max-w-xl text-sm leading-relaxed text-dim sm:text-[15px]">
            A finance agent pays the bills. <span className="font-semibold text-blue">Guard</span> checks every action it takes
            against the books. <span className="font-semibold text-red">Vandal</span> attacks a clone until the books break, names
            the broken link, and builds a control that Guard then enforces. Nothing here moves real money.
          </p>

          <div className="mt-8 text-[10px] uppercase tracking-[0.2em] text-faint">The loop</div>
          <ol className="mt-3 max-w-md" aria-label="The loop">
            {steps.map((st, i) => {
              const red = st.side === "red";
              const last = i === steps.length - 1;
              return (
                <li key={st.n} className="relative flex gap-4 pb-3 last:pb-0">
                  {!last && <span aria-hidden className="absolute left-[11px] top-6 h-[calc(100%-0.75rem)] w-px bg-line" />}
                  <span
                    className={cx(
                      "num relative mt-px flex size-6 shrink-0 items-center justify-center rounded-full border bg-bg text-[11px] font-bold",
                      red ? "border-red/70 text-red" : "border-blue/70 text-blue",
                    )}
                  >
                    {st.n}
                  </span>
                  <div className="min-w-0 pt-0.5">
                    <span className="text-sm font-semibold text-ink">{st.label}</span>
                    <span className="ml-2 text-xs text-faint">{red ? "Red" : "Blue"}</span>
                    <div className="text-xs leading-snug text-dim">{st.next.split(". ")[0].replace(/\.$/, "")}</div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        {/* Right: the three choices and the way in. */}
        <section className="flex flex-col gap-6 rounded-lg border border-line bg-panel/90 p-6 shadow-2xl backdrop-blur">
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-faint">Start on</div>
            <div role="radiogroup" aria-label="Side" className="grid gap-2">
              {SIDES.map((x) => {
                const red = x.id === "red";
                return (
                  <Choice key={x.id} on={side === x.id} red={red} onClick={() => setSide(x.id)} className={cx("border-l-4 p-3.5", red ? "border-l-red" : "border-l-blue")}>
                    <div className="flex items-center gap-2">
                      <span className={cx("text-xs font-black tracking-wider", red ? "text-red" : "text-blue")}>{x.name}</span>
                      <span className="text-sm font-semibold text-ink">{x.product}</span>
                      <span className="ml-auto text-[10px] text-faint">{x.first}</span>
                    </div>
                    <p className="mt-1 text-xs leading-snug text-dim">{x.blurb}</p>
                  </Choice>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-faint">Threat for Red to search</div>
            <div role="radiogroup" aria-label="Scenario" className="grid gap-1.5">
              {SCENARIOS.map((x) => (
                <Choice key={x.id} on={scenario === x.id} red onClick={() => setScenario(x.id)} title={x.hint} className="flex items-center gap-3 px-3 py-2">
                  <span className={cx("num text-[11px] font-black uppercase", scenario === x.id ? "text-red" : "text-faint")}>{x.id}</span>
                  <span className="text-ink">{x.label}</span>
                </Choice>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-faint">Finance agent</div>
            <div role="radiogroup" aria-label="Operator" className="grid grid-cols-2 gap-1.5">
              {OPERATORS.map((x) => (
                <Choice key={x.id} on={operator === x.id} onClick={() => setOperator(x.id)} title={x.hint} className="px-3 py-2">
                  <div className="text-ink">{x.label}</div>
                  <div className="mt-0.5 text-[11px] leading-snug text-faint">{x.hint}</div>
                </Choice>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3 border-t border-line pt-4">
            <span className="text-[11px] text-faint">All of this can be changed later.</span>
            <div className="ml-auto flex items-center gap-2">
              <Button tone="ghost" onClick={dismiss}>
                Skip
              </Button>
              <Button
                tone={side === "red" ? "red" : "blue"}
                onClick={enter}
                busy={entering}
                disabled={!s.ready}
                className="h-9 px-5 text-sm font-semibold"
              >
                {s.ready ? "Enter the war room →" : "Connecting…"}
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
