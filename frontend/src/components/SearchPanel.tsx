"use client";

import { atLabel, INVARIANTS, moveLine, moveTitle, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Move, OracleLabel } from "@/lib/types";
import { Badge, Button, Empty, LiveDot, Panel, SideTag } from "./ui";

const SCENARIOS = [
  { id: "a", label: "A · bank change after approval" },
  { id: "b", label: "B · bank fault, retry" },
  { id: "f", label: "F · refund redirection" },
];

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
      title="Adversarial search"
      tag={<SideTag side="red" />}
      className="min-h-[320px]"
      bodyClass="flex flex-col"
    >
      <div className="space-y-2 border-b border-line p-3">
        <div className="flex gap-1.5">
          <label className="sr-only" htmlFor="scenario">Scenario</label>
          <select
            id="scenario"
            value={search.scenario}
            onChange={(e) => s.setSearch({ scenario: e.target.value })}
            className="h-7 min-w-0 flex-1 rounded border border-line bg-raised px-1.5 text-xs"
          >
            {SCENARIOS.map((x) => (
              <option key={x.id} value={x.id}>
                {x.label}
              </option>
            ))}
          </select>
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

      <div className="flex-1 p-3">
        {!attack && !running && (
          <Empty>
            {r ? `No violation within depth ${r.depth} under ${policy}. Bounded claim: not a proof beyond it.` : "Search the attacker and fault alphabet for a sequence that breaks an invariant."}
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
            {r && r.findings.length > 1 && (
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
