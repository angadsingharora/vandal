"use client";

import { useEffect, useState } from "react";
import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { Button } from "./ui";

/** Every page load lands on the welcome screen, so a visitor always starts from the story.
 * The exceptions are the two places the welcome screen itself opens: the recorded loop
 * (`?mock=1`) and the workspace (`?workspace=1`); landing on the welcome again from either
 * would send them in a circle. `?welcome` forces it even then. */
export function wantsWelcome(): boolean {
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.has("welcome") || (params.get("mock") !== "1" && params.get("workspace") !== "1");
}

/** `?workspace=1`: the war room as a product, with nothing scripted. */
export function wantsWorkspace(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("workspace") === "1";
}

/** Keep (or drop) `?workspace=1` in the address bar without a reload, so a reload or a shared
 * link lands where the visitor chose. */
function markUrl(workspace: boolean) {
  const url = new URL(window.location.href);
  if (workspace) url.searchParams.set("workspace", "1");
  else url.searchParams.delete("workspace");
  url.searchParams.delete("welcome");
  window.history.replaceState(null, "", url.pathname + (url.search || ""));
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
const sideName = (side: Side) => (side === "strike" ? "Strike" : "Guard");

/** The landing: what Vandal is, in one screen, and two ways in. The guided demo starts the
 * same tour every time (the LLM Operator, on Guard's side, at step 1); the workspace is the
 * same war room with nothing scripted and every knob in its settings. */
export function Welcome({ onClose, onWorkspace }: { onClose: () => void; onWorkspace: () => void }) {
  const s = useWarRoom();
  const [entering, setEntering] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const mock = s.api?.mode === "mock";

  // Fade out, then unmount (200ms).
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onClose, 210);
    return () => clearTimeout(t);
  }, [leaving, onClose]);

  const start = async () => {
    if (entering || !s.ready) return;
    setEntering(true);
    s.setMode("demo");
    markUrl(false);
    try {
      await s.reset("v0");
    } finally {
      setEntering(false);
      setLeaving(true);
    }
  };

  // The workspace: same backend, same pages, no tour. Its settings open right away so the
  // first thing seen is what can be changed.
  const workspace = () => {
    if (entering) return;
    s.setMode("workspace");
    markUrl(true);
    setLeaving(true);
    onWorkspace();
  };

  // The whole loop from a recording of the real backend, replayed in the browser: no host to
  // wait on. The top bar's RECORDED chip leads back to the live backend.
  const watch = () => window.location.assign("/?mock=1");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Enter" && start();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const status = s.ready ? null : s.waking ? "Waking the host…" : s.error ? "The API is not answering." : "Connecting…";

  return (
    <div className={cx("fixed inset-0 z-50 overflow-y-auto overflow-x-hidden bg-panel", leaving ? "welcome-leave" : "welcome-enter")}>
      <div role="dialog" aria-modal aria-labelledby="welcome-title" className="mx-auto w-full max-w-5xl px-6 py-10 sm:px-10 lg:py-16">
        <header className="flex items-baseline justify-between gap-4">
          <span className="text-base font-semibold tracking-tight text-ink">Vandal</span>
          <span className="text-xs text-faint">Security for AI finance agents</span>
        </header>

        {/* The problem, the product, the way in. */}
        <section className="mt-20 max-w-3xl lg:mt-28">
          <h1 id="welcome-title" className="text-4xl font-semibold leading-[1.08] tracking-tight text-ink sm:text-5xl">
            Your books can balance perfectly while the money goes to the wrong person.
          </h1>
          <p className="mt-6 max-w-2xl text-[15px] leading-relaxed text-dim">
            Companies are handing accounts payable to AI agents. The controls those agents rely on were built for human clerks: one
            email from a lookalike domain, landing after an invoice is approved and before the payment run, sends a vendor&apos;s
            payment to an attacker. Every step looks valid and the ledger still balances.
          </p>
          <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-dim">
            Vandal checks every action before money moves, and keeps attacking its own checks so they get stronger with every change.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button tone="blue" onClick={start} busy={entering} disabled={!s.ready} className="h-10 px-5 text-sm font-semibold">
              {status ?? "Start the demo"}
            </Button>
            {!mock && (
              <Button onClick={workspace} disabled={!s.ready} className="h-10 px-5 text-sm font-semibold" title="No tour. Every knob is in the settings.">
                Open the workspace
              </Button>
            )}
            {!mock && (
              <button
                type="button"
                onClick={watch}
                className="h-10 px-2 text-sm text-dim underline-offset-4 hover:text-ink hover:underline"
                title="The seven steps from a recording made against the real backend, replayed in the browser. No waiting on a host."
              >
                Watch the recorded loop
              </button>
            )}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-faint">
            The demo is a guided seven-step loop on Bayline Property Group, a simulated property manager with 80 vendor invoices and
            a $25,000 approval threshold. The workspace is the same war room with nothing scripted: your company, your rules, your
            attacker. No real money moves in either.
          </p>
        </section>

        {/* The three parts. */}
        <section className="mt-20 grid gap-8 border-t border-line pt-8 sm:grid-cols-3" aria-label="The three parts">
          {PARTS.map((p) => (
            <div key={p.name}>
              <h2 className={cx("text-sm font-semibold", tone(p.side))}>{p.name}</h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-dim">{p.blurb}</p>
            </div>
          ))}
        </section>

        {/* The loop. */}
        <section className="mt-16 border-t border-line pt-8" aria-label="The loop">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-faint">The loop, in seven steps</h2>
          <ol className="mt-5 grid gap-x-10 gap-y-4 sm:grid-cols-2">
            {STEPS.map((st, i) => (
              <li key={st.label} className="flex gap-3">
                <span className="num w-5 shrink-0 pt-px text-xs text-faint">{i + 1}</span>
                <div className="min-w-0">
                  <span className="text-[13px] font-semibold text-ink">{st.label}</span>
                  <span className={cx("ml-2 text-[11px] font-medium", tone(st.side))}>{sideName(st.side)}</span>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-dim">{st.what}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <footer className="mt-16 border-t border-line pt-6 text-xs leading-relaxed text-faint">
          Fixes go into Guard&apos;s rules, never into the agent: no retraining, no prompt edits. The protection holds whichever agent
          does the work.
        </footer>
      </div>
    </div>
  );
}
