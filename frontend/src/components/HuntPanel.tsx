"use client";

// R13: Red's threat hunter, the other way to find an attack on the Attack page. Claude reads
// this company's books and controls, proposes an attack nobody wrote down, the twin runs it,
// and what Guard did feeds the next attempt.

import { usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { HuntAttempt } from "@/lib/types";
import { MovesTimeline } from "./SearchPanel";
import { Badge, Block, Button, LiveDot } from "./ui";

const ATTEMPTS = 6;

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
      label="Or let Claude hunt"
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
              ? "The hunt needs Claude: set ANTHROPIC_API_KEY on the backend."
              : "Instead of a preset threat, Claude studies this company's vendors, invoices, credits and controls, then invents attacks the search doesn't try. Each attempt runs on the twin, and what Guard did feeds the next one."}
          </p>
        )}
        {running && hunt.attempts.length === 0 && <p className="text-xs text-dim">Claude is studying the books…</p>}
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
