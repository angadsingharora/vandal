"use client";

// One page per step of the loop. The header says which step this is and what it does, the
// body is the step's own content, and the footer holds the single way forward. The footer
// button breathes (nudge) once this step's work is done and the next step's isn't, so the eye
// always has somewhere to go.

import type { ReactNode } from "react";
import { cx } from "@/lib/format";
import { currentStep, loopSteps, stepOf, type Stage } from "@/lib/loop";
import { useWarRoom } from "@/lib/store";
import { Button } from "./ui";

export function useLoop() {
  const s = useWarRoom();
  const steps = loopSteps(s.progress());
  return { steps, now: currentStep(steps), stage: s.stage };
}

export interface NextAction {
  label: string;
  onClick: () => void;
  /** Can be clicked now. */
  ready: boolean;
  busy?: boolean;
  /** One line next to the button: what clicking it does, or what is missing. */
  hint?: ReactNode;
  tone?: "red" | "blue" | "default";
  /** Override the default nudge (ready, this step done, the next one not). */
  nudge?: boolean;
}

export function StagePage({
  stage,
  lede,
  actions,
  next,
  fill,
  children,
}: {
  stage: Stage;
  lede: ReactNode;
  actions?: ReactNode;
  next?: NextAction;
  /** Fill the viewport with a fixed grid instead of a scrolling column. */
  fill?: boolean;
  children: ReactNode;
}) {
  const { steps, now } = useLoop();
  const step = stepOf(steps, stage);
  const following = steps[step.n] as (typeof steps)[number] | undefined;
  const red = step.side === "red";
  const nudge = next ? (next.nudge ?? (next.ready && step.done && !(following?.done ?? true))) : false;

  return (
    <div className={cx("flex min-h-0 flex-1 flex-col", !fill && "overflow-y-auto")}>
      <header
        className={cx(
          "flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-l-4 px-5 py-2.5",
          red ? "border-b-red/20 border-l-red bg-red/[0.04]" : "border-b-blue/20 border-l-blue bg-blue/[0.04]",
        )}
      >
        <div className="min-w-0 flex-1 basis-80">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className={cx("num text-[10px] font-bold uppercase tracking-[0.18em]", red ? "text-red" : "text-blue")}>
              Step {step.n} of {steps.length} · {red ? "Vandal Strike" : "Vandal Guard"}
            </span>
            {step.done ? (
              <span className="text-[10px] uppercase tracking-wider text-ok">done</span>
            ) : now?.id === stage ? (
              <span className="text-[10px] uppercase tracking-wider text-warn">up next</span>
            ) : null}
          </div>
          <h1 className="text-base font-semibold leading-tight text-ink">{step.label}</h1>
          <p className="mt-0.5 max-w-3xl text-xs leading-snug text-dim">{lede}</p>
        </div>
        {actions && <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>}
      </header>

      {/* A scrolling page grows with its content (min-height auto) so the sticky footer follows it;
          a filled page is pinned to the viewport and its panels scroll inside. */}
      <div className={cx(fill ? "flex min-h-0 flex-1 flex-col" : "mx-auto w-full max-w-6xl grow space-y-4 px-5 py-4")}>{children}</div>

      {next && (
        <footer className="sticky bottom-0 z-20 flex shrink-0 items-center gap-3 border-t border-line bg-panel/95 px-5 py-2 backdrop-blur">
          <span className="min-w-0 flex-1 truncate text-xs text-dim">
            {next.hint ?? (next.ready && following ? `Next: ${following.next}` : "")}
          </span>
          <Button
            tone={next.tone ?? following?.side ?? "default"}
            onClick={next.onClick}
            disabled={!next.ready}
            busy={next.busy}
            nudge={nudge}
            className="h-8 px-4 text-[13px] font-semibold"
          >
            {next.label}
          </Button>
        </footer>
      )}
    </div>
  );
}
