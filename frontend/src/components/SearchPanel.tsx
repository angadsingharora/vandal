"use client";

// A sequence of attacker moves drawn as a timeline, shared by the Attack page and the inject
// dialog.

import { atLabel, moveLine, moveTitle } from "@/lib/format";
import type { Move, OracleLabel } from "@/lib/types";

export function MovesTimeline({ moves, labels, judge }: { moves: Move[]; labels?: OracleLabel[]; judge?: boolean }) {
  return (
    <ol className="relative ml-2 border-l border-line">
      {moves.map((m, i) => (
        <li key={i} className="relative pb-3 pl-4 last:pb-1">
          <span className="absolute -left-[7px] top-0.5 flex size-3.5 items-center justify-center rounded-full border border-red/60 bg-bg text-[8px] font-bold text-red">
            {i + 1}
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-xs font-medium text-ink">{moveTitle(m)}</span>
            <span className="text-[10px] text-faint">{atLabel(m.at)}</span>
          </div>
          <div className="num break-all text-[11px] text-dim">{moveLine(m)}</div>
          {typeof m.params.text === "string" && (
            <blockquote className="mt-1 border-l-2 border-line pl-2 text-[11px] italic text-dim">
              {String(m.params.text).replace(/\s+/g, " ").slice(0, 180)}
            </blockquote>
          )}
        </li>
      ))}
      {judge && labels && labels.length > 0 && (
        <li className="relative pl-4">
          <div className="rounded border border-esc/40 bg-esc/10 p-2 text-[11px] text-esc">
            <div className="mb-1 font-semibold">Answer key</div>
            {labels.map((l, i) => (
              <div key={i} className="num break-all">
                {l.subject} → {l.label}
                {typeof l.value === "string" ? ` = ${l.value}` : ""}
              </div>
            ))}
          </div>
        </li>
      )}
    </ol>
  );
}
