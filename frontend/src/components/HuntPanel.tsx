"use client";

// R13: the hunt, the other way to find an attack on the Attack page. It studies
// this company's books and controls, tries an attack from outside the preset search, the twin
// runs it, and what Guard did feeds the next attempt.

import { useEffect, useState } from "react";

import { usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { HuntAttempt } from "@/lib/types";
import { MovesTimeline } from "./SearchPanel";
import { Badge, Block, Button, LiveDot } from "./ui";

const ATTEMPTS = 6;

/** What the hunt is "doing" during the pause before an attempt lands, one line a second. */
const THINKING = [
  "Studying the books: open invoices, approvals, accounts on file…",
  "Reading the active controls for a gap between the check and the money…",
  "Weighing a hypothesis against what Guard did last time…",
  "Running it on the twin…",
];

function Thinking({ attempt }: { attempt: number }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    setI(0);
    const t = setInterval(() => setI((x) => (x + 1) % THINKING.length), 1000);
    return () => clearInterval(t);
  }, [attempt]);
  return (
    <p className="flex items-center gap-1.5 text-xs text-dim" aria-live="polite">
      <LiveDot className="text-red" />
      <span className="num text-[10px] font-bold text-red">{attempt}</span>
      <span>{THINKING[i]}</span>
    </p>
  );
}

/** The check that stopped an attempt, from Guard's first hold/escalate/block line. */
function stoppedBy(a: HuntAttempt): string | null {
  const line = a.outcome.guard.find((g) => !g.includes("approval.threshold")) ?? a.outcome.guard[0];
  return line ? (line.split("fired: ")[1] ?? null) : null;
}

function Outcome({ a }: { a: HuntAttempt }) {
  const o = a.outcome;
  if (o.violated.length) {
    return (
      <Badge tone="bad">
        broke {o.violated.join(", ")} · {usd(o.exposure, { cents: false })}
      </Badge>
    );
  }
  if (!a.moves.length) return <Badge tone="warn">couldn&apos;t run</Badge>;
  const by = stoppedBy(a);
  return <Badge tone="ok">held{by ? ` · ${by}` : ""}</Badge>;
}

export function HuntPanel({ quiet }: { quiet?: boolean }) {
  const s = useWarRoom();
  const { hunt } = s;
  const running = hunt.phase === "running";
  const best = hunt.result?.best;
  const policy = s.summary?.policy ?? "v0";
  const needsKey = hunt.phase === "failed" && hunt.attempts.length === 0;

  return (
    <Block
      label="Or hunt"
      quiet={quiet}
      aside={
        <>
          {running && (
            <span className="flex items-center gap-1.5">
              <LiveDot className="text-red" /> attempt {hunt.attempts.length + 1} of {ATTEMPTS}
            </span>
          )}
          <Button tone="red" onClick={() => s.runHunt(ATTEMPTS)} busy={running} disabled={!s.ready} className="h-6">
            Hunt on {policy}
          </Button>
        </>
      }
    >
      <div className="space-y-2 p-3">
        {!hunt.attempts.length && !running && (
          <p className="text-xs leading-snug text-dim">
            {needsKey
              ? "The hunt didn't start. It needs a backend with the hunt route (main, PR 40 or later)."
              : "Instead of a preset threat, the hunt studies this company's vendors, invoices, credits and controls, then tries attacks the search doesn't. Each attempt runs on the twin, and what Guard did feeds the next one."}
          </p>
        )}
        {hunt.attempts.length > 0 && (
          <ol className="space-y-1.5">
            {hunt.attempts.map((a) => (
              <li key={a.n}>
                <details className="group rounded border border-line bg-raised/40 open:bg-raised/70">
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-2 py-1.5">
                    <span className="num text-[10px] font-bold text-red">{a.n}</span>
                    <span className="min-w-0 flex-1 truncate text-xs text-ink" title={a.weak_spot}>
                      {a.weak_spot}
                    </span>
                    <Outcome a={a} />
                  </summary>
                  <div className="space-y-2 border-t border-line px-2 py-2">
                    <p className="text-[11px] leading-relaxed text-dim">{a.rationale}</p>
                    {a.moves.length > 0 && <MovesTimeline moves={a.moves} />}
                    {a.outcome.dropped.map((d) => (
                      <div key={d} className="num break-all text-[10px] text-warn">
                        dropped {d}
                      </div>
                    ))}
                  </div>
                </details>
              </li>
            ))}
          </ol>
        )}
        {running && <Thinking attempt={hunt.attempts.length + 1} />}
        {hunt.result && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-2 text-[11px] text-dim">
            <span>{hunt.result.reason}</span>
            {best && (
              <Badge tone={best.outside_preset_search ? "esc" : "dim"}>
                {best.outside_preset_search ? "outside the preset search" : "inside a preset family"}
              </Badge>
            )}
          </div>
        )}
      </div>
    </Block>
  );
}
