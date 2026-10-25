"use client";

import { atLabel, cx, INVARIANTS, moveLine, moveTitle, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Move, OracleLabel } from "@/lib/types";
import { Badge, Button, Empty, LiveDot, Panel } from "./ui";

export const SCENARIOS = [
  { id: "a", label: "Bank change after approval", hint: "A vendor's bank details change between approval and the payment run" },
  { id: "b", label: "Bank fault, then a retry", hint: "The bank drops an ack, the Operator retries, the vendor is paid twice" },
  { id: "f", label: "Refund redirection", hint: "An overpayment, then a refund request to a different account" },
];

/** The counterexample as a numbered sequence: it really is one. */
export function MovesTimeline({ moves, labels, judge }: { moves: Move[]; labels?: OracleLabel[]; judge?: boolean }) {
  return (
    <ol className="space-y-2.5">
      {moves.map((m, i) => (
        <li key={i} className="flex gap-2.5">
          <span className="num mt-px flex size-4 shrink-0 items-center justify-center rounded-full bg-red text-[11px] font-medium leading-none text-bg">
            {i + 1}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[12.5px] font-medium text-ink">{moveTitle(m)}</span>
              <span className="num text-[11px] text-dim">{atLabel(m.at)}</span>
            </div>
            <div className="num break-all text-[11px] text-dim">{moveLine(m)}</div>
            {typeof m.params.text === "string" && (
              <div className="mt-1 bg-raised/40 px-2 py-1 text-[11px] text-dim">{String(m.params.text).replace(/\s+/g, " ").slice(0, 180)}</div>
            )}
          </div>
        </li>
      ))}
      {judge && labels && labels.length > 0 && (
        <li className="ml-[26px] border-l-2 border-esc pl-2 text-[11px]">
          <div className="font-medium text-esc">Answer key</div>
          {labels.map((l, i) => (
            <div key={i} className="num break-all text-dim">
              {l.subject}: {l.label}
              {typeof l.value === "string" ? ` = ${l.value}` : ""}
            </div>
          ))}
        </li>
      )}
    </ol>
  );
}

export function SearchPanel() {
  const s = useWarRoom();
  const { search, attack } = s;
  const running = search.phase === "running";
  const r = search.result;
  const policy = s.summary?.policy ?? "v0";
  const replayed = s.replays.before;

  return (
    <Panel title="Attack" className="min-h-[320px]" bodyClass="flex flex-col">
      <div role="radiogroup" aria-label="Scenario">
        {SCENARIOS.map((x) => {
          const on = search.scenario === x.id;
          return (
            <button
              key={x.id}
              role="radio"
              aria-checked={on}
              onClick={() => s.setSearch({ scenario: x.id })}
              title={x.hint}
              className={cx(
                "flex w-full items-center gap-2.5 border-b border-line px-3 py-1.5 text-left text-[12px] transition-colors",
                on ? "bg-raised text-ink" : "text-dim hover:text-ink",
              )}
            >
              <span className={cx("flex size-3 shrink-0 items-center justify-center rounded-full border", on ? "border-red" : "border-faint")}>
                {on && <span className="size-1.5 rounded-full bg-red" />}
              </span>
              <span className="flex-1">{x.label}</span>
              <span className="num text-[11px] text-dim">{x.id}</span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2 px-3 py-2">
        <label htmlFor="depth" className="text-[11px] text-dim" title="How many attacker moves or faults per sequence">
          Moves per sequence
        </label>
        <select
          id="depth"
          value={search.depth}
          onChange={(e) => s.setSearch({ depth: Number(e.target.value) })}
          className="num h-7 rounded border border-ink/20 bg-bg px-1.5 text-[12px]"
        >
          {[1, 2, 3, 4].map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <div className="border-b border-line px-3 pb-3">
        <Button tone="red" className="w-full justify-center" onClick={s.runSearch} busy={running} disabled={!s.ready}>
          Unleash Vandal on {policy}
        </Button>
      </div>

      <div className="grid grid-cols-2 border-b border-line">
        <div className="border-r border-line px-3 py-1.5">
          <div className="flex items-center gap-1.5 text-[11px] text-dim">Sequences tried {running && <LiveDot className="text-red" />}</div>
          <div className="num text-[17px] font-semibold leading-tight text-ink">{search.explored.toLocaleString()}</div>
        </div>
        <div className="px-3 py-1.5">
          <div className="text-[11px] text-dim">Violations</div>
          <div className={cx("num text-[17px] font-semibold leading-tight", r?.findings.length ? "text-red" : "text-ink")}>
            {r ? r.findings.length : running ? "…" : "—"}
          </div>
        </div>
      </div>
      {running && <div className="border-b border-line px-3 py-1.5 text-[11px] text-dim">Exploring depth {search.atDepth}</div>}
      {r && (
        <details className="border-b border-line px-3 py-1.5 text-[11px] text-dim">
          <summary className="cursor-pointer">Search stats</summary>
          <div className="num mt-1 leading-snug">
            depth {r.depth}, alphabet {r.alphabet}, per depth [{r.levels.join(", ")}], {r.deduped} deduped, {r.pruned} pruned,{" "}
            {Math.round(r.runs_per_second)} runs/s
          </div>
        </details>
      )}

      <div className="flex-1 p-3">
        {!attack && !running && (
          <Empty>
            {r
              ? `No violation within depth ${r.depth} under ${policy}.`
              : "Vandal tries every short sequence of attacker moves and bank faults against the copy."}
          </Empty>
        )}
        {attack && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-[14px] font-medium text-ink">Counterexample</span>
              <span className="text-[11px] text-dim">{attack.source === "inject" ? "from your scenario" : `under ${attack.policy}`}</span>
            </div>
            <MovesTimeline moves={attack.finding.moves} labels={attack.labels} judge={s.judge} />
            <div className="border-y border-line py-1.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[11px] text-dim">Misdirected</span>
                <span className="num text-[17px] font-semibold leading-tight text-red">{usd(attack.finding.exposure)}</span>
              </div>
              {attack.finding.violated.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                  {attack.finding.violated.map((v) => (
                    <Badge key={v} tone="bad" title={INVARIANTS[v]}>
                      {v}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            {r && attack.source === "search" && r.findings.length > 1 && (
              <details className="text-[11px] text-dim">
                <summary className="cursor-pointer">{r.findings.length} violating traces at this depth</summary>
                <ul className="num mt-1 space-y-1">
                  {r.findings.map((f, i) => (
                    <li key={i} className="break-all">
                      {f.moves.map(moveLine).join(", then ")} ({usd(f.exposure, { cents: false })})
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div className="flex flex-wrap gap-1.5">
              <Button onClick={() => s.replayAttack(attack.policy)} title="Run the counterexample on a fresh clone and show its books">
                Replay on the copy
              </Button>
              <Button tone="red" onClick={s.diagnose} busy={s.diagnosis.phase === "running"}>
                Diagnose
              </Button>
            </div>
            {replayed && (
              <div className="text-[11px] text-dim">
                Replayed on a fresh clone:{" "}
                {["INV-1", "INV-7"].some((v) => replayed.result.violated.includes(v)) ? "the books don't tie out" : "the books balance"}, and{" "}
                {replayed.result.violated.length ? `${replayed.result.violated.join(", ")} broke` : "nothing broke"}.
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
