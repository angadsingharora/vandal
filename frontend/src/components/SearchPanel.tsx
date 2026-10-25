"use client";

import { atLabel, cx, INVARIANTS, moveLine, moveTitle, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Move, OracleLabel } from "@/lib/types";
import { Badge, Button, Empty, LiveDot, Panel, SideTag } from "./ui";

const SCENARIOS = [
  { id: "all", label: "All threats", hint: "Every attacker move and bank fault in one search, so Vandal isn't told where to look" },
  { id: "a", label: "Bank change after approval", hint: "A vendor's bank details change between approval and the payment run" },
  { id: "b", label: "Bank fault, retry", hint: "The bank drops an ack, the Operator retries, the vendor is paid twice" },
  { id: "f", label: "Refund redirection", hint: "An overpayment, then a refund request to a different account" },
];
const FAMILIES = SCENARIOS.filter((x) => x.id !== "all");

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

export function SearchPanel() {
  const s = useWarRoom();
  const { search, attack } = s;
  const running = search.phase === "running";
  const r = search.result;
  const policy = s.summary?.policy ?? "v0";
  const replayed = s.replays.before;

  return (
    <Panel
      title="Attack · adversarial search"
      tag={<SideTag side="red" />}
      className="min-h-[320px]"
      bodyClass="flex flex-col"
    >
      <div className="space-y-2 border-b border-line p-3">
        <div className="text-[10px] uppercase tracking-wider text-faint">Threat to search</div>
        <div role="radiogroup" aria-label="Scenario" className="flex flex-col gap-1">
          {SCENARIOS.map((x) => {
            const on = search.scenario === x.id;
            return (
              <button
                key={x.id}
                role="radio"
                aria-checked={on}
                onClick={() =>
                  // The combined window is ~4x the moves: k=2 takes seconds, k=3 can take a minute
                  // once a family is closed (search runs to full depth looking for it).
                  s.setSearch(x.id === "all" && search.depth > 2 ? { scenario: x.id, depth: 2 } : { scenario: x.id })
                }
                title={x.hint}
                className={cx(
                  "flex items-center gap-2 rounded border px-2 py-1 text-left text-xs transition-colors",
                  on ? "border-red/70 bg-red/10 text-ink" : "border-line text-dim hover:border-dim hover:text-ink",
                )}
              >
                <span className={cx("num text-[10px] font-bold uppercase", on ? "text-red" : "text-faint")}>{x.id}</span>
                {x.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-dim" title="How many attacker moves or faults per sequence">Moves per sequence</span>
          <label className="sr-only" htmlFor="depth">Depth</label>
          <select
            id="depth"
            value={search.depth}
            onChange={(e) => s.setSearch({ depth: Number(e.target.value) })}
            className="num h-7 rounded border border-line bg-raised px-1.5 text-xs"
            title="Moves per sequence"
          >
            {[1, 2, 3, 4].map((d) => (
              <option key={d} value={d}>
                k={d}
              </option>
            ))}
          </select>
        </div>
        <Button tone="red" className="w-full justify-center" onClick={s.runSearch} busy={running} disabled={!s.ready}>
          Unleash Vandal on {policy}
        </Button>
      </div>

      <div className="grid grid-cols-2 border-b border-line">
        <div className="border-r border-line px-3 py-2">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-faint">
            Sequences {running && <LiveDot className="text-red" />}
          </div>
          <div className="num text-2xl font-semibold text-ink">{search.explored.toLocaleString()}</div>
        </div>
        <div className="px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-faint">Violations</div>
          <div className={`num text-2xl font-semibold ${r?.findings.length ? "text-bad" : "text-ink"}`}>
            {r ? r.findings.length : running ? "…" : "—"}
          </div>
        </div>
      </div>
      {running && <div className="px-3 py-1.5 text-[11px] text-dim">exploring depth {search.atDepth}…</div>}
      {r && (
        <div className="num border-b border-line px-3 py-1.5 text-[11px] text-dim">
          depth {r.depth} · alphabet {r.alphabet} · per depth [{r.levels.join(", ")}] · {r.deduped} deduped ·{" "}
          {r.pruned} pruned · {Math.round(r.runs_per_second)} runs/s
        </div>
      )}
      {r?.scenario === "all" && (
        <div className="space-y-1 border-b border-line px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-faint">Found per threat family</div>
          {FAMILIES.map((fam) => {
            const f = r.by_family?.[fam.id];
            return (
              <div key={fam.id} className="flex items-baseline justify-between gap-2 text-[11px]" title={fam.hint}>
                <span className="flex items-baseline gap-1.5 text-dim">
                  <span className={cx("num font-bold uppercase", f ? "text-red" : "text-faint")}>{fam.id}</span>
                  {fam.label}
                </span>
                {f ? (
                  <span className="num shrink-0 text-bad">
                    {f.moves.length} move{f.moves.length === 1 ? "" : "s"} · {usd(f.exposure, { cents: false })}
                  </span>
                ) : (
                  <span className="shrink-0 text-faint">none within k={r.depth}</span>
                )}
              </div>
            );
          })}
          {r.by_family?.all && (
            <div className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="text-dim">Mixed attack across families</span>
              <span className="num shrink-0 text-bad">
                {r.by_family.all.moves.length} moves · {usd(r.by_family.all.exposure, { cents: false })}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="flex-1 p-3">
        {!attack && !running && (
          <Empty>
            {r ? `No violation within depth ${r.depth} under ${policy}. Bounded claim: not a proof beyond it.` : "Vandal tries every short sequence of attacker moves and bank faults against the twin, looking for one that sends money to the wrong place."}
          </Empty>
        )}
        {attack && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-dim">Minimal counterexample</span>
              <Badge tone="dim">{attack.source === "inject" ? "from your scenario" : `under ${attack.policy}`}</Badge>
            </div>
            <MovesTimeline moves={attack.finding.moves} labels={attack.labels} judge={s.judge} />
            <div className="rounded border border-bad/40 bg-bad/10 p-2">
              <div className="flex items-baseline justify-between">
                <span className="text-[11px] text-bad">Money misdirected</span>
                <span className="num text-lg font-bold text-bad">{usd(attack.finding.exposure)}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {attack.finding.violated.map((v) => (
                  <span key={v} title={INVARIANTS[v]}>
                    <Badge tone="bad">{v}</Badge>
                  </span>
                ))}
              </div>
            </div>
            {r && attack.source === "search" && r.findings.length > 1 && (
              <details className="text-[11px] text-dim">
                <summary className="cursor-pointer">{r.findings.length} violating traces at this depth</summary>
                <ul className="num mt-1 space-y-1">
                  {r.findings.map((f, i) => (
                    <li key={i} className="break-all">
                      {f.moves.map(moveLine).join(" → ")} · {usd(f.exposure, { cents: false })}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <div className="flex flex-wrap gap-1.5">
              <Button onClick={() => s.replayAttack(attack.policy)} title="Run the counterexample on a fresh clone and show its books">
                Replay on twin
              </Button>
              <Button tone="red" onClick={s.diagnose} busy={s.diagnosis.phase === "running"}>
                Diagnose
              </Button>
            </div>
            {replayed && (
              <div className="text-[11px] text-dim">
                Replayed on a fresh clone:{" "}
                {["INV-1", "INV-7"].some((v) => replayed.result.violated.includes(v)) ? "the books don't tie out" : "the books balance"}
                , and {replayed.result.violated.length ? `${replayed.result.violated.join(", ")} broke` : "nothing broke"}.
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}
