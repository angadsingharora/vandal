"use client";

import { useEffect, useState } from "react";
import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
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

type Side = "guard" | "strike";

const PARTS: { side: Side | "operator"; name: string; blurb: string }[] = [
  {
    side: "operator",
    name: "The Operator",
    blurb: "The AI finance agent, built on Claude. It reads invoices, asks for approvals, pays vendors, and keeps the books.",
  },
  {
    side: "guard",
    name: "Vandal Guard",
    blurb: "Sits in front of the agent. Checks every payment, bank change, and refund against independent records, then allows, holds, or escalates it.",
  },
  {
    side: "strike",
    name: "Vandal Strike",
    blurb: "Attacks a sandboxed copy of the books, finds what gets past Guard, then builds a fix and proves it works.",
  },
];

// The same seven steps as the loop strip (lib/loop.ts), worded for a first-time viewer.
const STEPS: { side: Side; label: string; what: string }[] = [
  { side: "guard", label: "Operate", what: "The agent works a week of the company's books. Guard checks every action." },
  { side: "strike", label: "Attack", what: "Strike searches a copy of the books for events that send money to the wrong place." },
  { side: "strike", label: "Diagnose", what: "Finds the broken link between what was approved and what was paid." },
  { side: "strike", label: "Fix", what: "Claude proposes rules for Guard; Strike attacks each one until one survives." },
  { side: "strike", label: "Prove", what: "Six checks, including attacks it never saw and every legitimate payment still going through." },
  { side: "guard", label: "Approve", what: "A human controller signs off. Neither the agent nor Strike can approve a rule." },
  { side: "guard", label: "Enforce", what: "Guard applies the rule. The same attack is replayed and held: $0 moves." },
];

const tone = (side: Side | "operator") => (side === "strike" ? "text-red" : side === "guard" ? "text-blue" : "text-ink");

/** First-visit landing: the business problem, the three parts, the loop, and one way in. Every visit starts the
 * same demo: the LLM Operator, on Guard's side, at step 1. */
export function Welcome({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const [entering, setEntering] = useState(false);
  const [leaving, setLeaving] = useState(false);

  // Fade out, then unmount. The card's leave animation is 200ms; the backdrop's 220ms.
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onClose, 230);
    return () => clearTimeout(t);
  }, [leaving, onClose]);

  const start = async () => {
    if (entering || !s.ready) return;
    setEntering(true);
    try {
      window.localStorage.setItem(WELCOME_KEY, "1");
    } catch {
      /* private mode: show it again next time */
    }
    try {
      if (s.operator !== "llm" || s.summary?.operator !== "llm") await s.reset(s.summary?.policy ?? "v0", "llm");
      await s.setView("blue");
    } finally {
      setEntering(false);
      setLeaving(true);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Enter" && start();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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
        {/* Left: the business problem and what Vandal is. */}
        <section className="flex flex-col justify-center">
          <div className="text-xs uppercase tracking-[0.3em] text-faint">Welcome to</div>
          <h1 id="welcome-title" className="mt-2 text-6xl font-black leading-none tracking-[0.2em] text-ink sm:text-7xl lg:text-8xl">
            VANDAL
          </h1>
          <p className="mt-5 max-w-xl text-lg font-semibold leading-snug text-ink">
            Your books can balance perfectly while the money goes to the wrong person.
          </p>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-dim sm:text-[15px]">
            Companies are handing accounts payable to AI agents: paying vendors, changing bank details, issuing refunds. The
            controls they rely on were built for human clerks. A single email from a lookalike domain, landing after an invoice is
            approved and before the payment run, can send a vendor's payment to an attacker. Every step looks valid and the ledger
            still balances.
          </p>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-dim sm:text-[15px]">
            Vandal is the security layer for those agents. It checks every action before money moves, and it keeps attacking its own
            checks so they get stronger with every change.
          </p>

          <div className="mt-8 grid max-w-2xl gap-3 sm:grid-cols-3">
            {PARTS.map((p) => (
              <div key={p.name} className="rounded border border-line bg-panel/70 p-3">
                <div className={cx("text-sm font-semibold", tone(p.side))}>{p.name}</div>
                <p className="mt-1 text-xs leading-snug text-dim">{p.blurb}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 max-w-2xl text-xs leading-relaxed text-faint">
            Fixes go into Guard's rules, never into the agent: no retraining, no prompt edits. The protection holds whichever agent
            does the work.
          </p>
        </section>

        {/* Right: the demo company, the loop, and the way in. */}
        <section className="flex flex-col gap-6 rounded-lg border border-line bg-panel/90 p-6 shadow-2xl backdrop-blur">
          <div>
            <div className="mb-2 text-[10px] uppercase tracking-[0.2em] text-faint">Today's company</div>
            <p className="text-sm leading-relaxed text-dim">
              <span className="font-semibold text-ink">Bayline Property Group</span>, a property manager with 12 buildings in the
              Bay Area. Its AI agent handles 80 vendor invoices; anything over $25,000 needs a controller's approval. Everything here is
              simulated. No real money moves.
            </p>
          </div>

          <div>
            <div className="mb-3 text-[10px] uppercase tracking-[0.2em] text-faint">The demo, in seven steps</div>
            <ol aria-label="The demo loop">
              {STEPS.map((st, i) => {
                const strike = st.side === "strike";
                const last = i === STEPS.length - 1;
                return (
                  <li key={st.label} className="relative flex gap-4 pb-3 last:pb-0">
                    {!last && <span aria-hidden className="absolute left-[11px] top-6 h-[calc(100%-0.75rem)] w-px bg-line" />}
                    <span
                      className={cx(
                        "num relative mt-px flex size-6 shrink-0 items-center justify-center rounded-full border bg-bg text-[11px] font-bold",
                        strike ? "border-red/70 text-red" : "border-blue/70 text-blue",
                      )}
                    >
                      {i + 1}
                    </span>
                    <div className="min-w-0 pt-0.5">
                      <span className="text-sm font-semibold text-ink">{st.label}</span>
                      <span className={cx("ml-2 text-xs", tone(st.side))}>{strike ? "Vandal Strike" : "Vandal Guard"}</span>
                      <div className="text-xs leading-snug text-dim">{st.what}</div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="flex items-center gap-3 border-t border-line pt-4">
            <span className="text-[11px] text-faint">Starts at step 1 with Vandal Guard.</span>
            <Button tone="blue" onClick={start} busy={entering} disabled={!s.ready} className="ml-auto h-9 px-5 text-sm font-semibold">
              {s.ready ? "Start the demo →" : "Connecting…"}
            </Button>
          </div>
        </section>
      </div>
    </div>
  );
}
