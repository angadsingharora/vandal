"use client";

// Step 2, Red. One column, top to bottom: release the strike; what the search found (the safe
// sequences as a number, the ones that broke the books in full); the minimal counterexample; the
// evidence. The footer carries the attack to Diagnose. The strike never says what it is looking
// for: it searches every threat family and reports what broke.

import { cx, INVARIANTS, moveLine, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { EvidenceScan } from "./EvidenceScan";
import { HuntPanel } from "./HuntPanel";
import { MovesTimeline } from "./SearchPanel";
import { StagePage } from "./Stage";
import { Badge, Block, Button, LiveDot, Reveal, Stat } from "./ui";

export function AttackPage({ onInject }: { onInject: () => void }) {
  const s = useWarRoom();
  const { search, attack, hunt } = s;
  const running = search.phase === "running";
  const hunting = hunt.phase === "running";
  const maxDepth = s.settings?.limits?.max_depth ?? 6;
  const hunted = attack?.source === "hunt";
  const r = search.result;
  const policy = attack?.policy ?? s.tabs.find((t) => t.kind === "live")?.policy ?? "v0";
  const before = s.replays.before;
  const violations = before?.result.violations ?? [];

  const broke = hunted ? (hunt.result?.hits ?? 1) : r ? r.findings.length : attack ? 1 : 0;
  const explored = hunted ? hunt.attempts.length : running ? search.explored : r ? r.explored : (s.inject.result?.explored ?? 0);
  const safe = Math.max(explored - broke, 0);
  const sig = (f: { moves: { kind: string; params: Record<string, string | number> }[] }) => f.moves.map((m) => moveLine(m as never)).join("→");

  const goDiagnose = () => {
    void s.setStage("diagnose");
    if (s.diagnosis.phase !== "done" && s.diagnosis.phase !== "running") void s.diagnose();
  };

  return (
    <StagePage
      stage="attack"
      lede={
        <>
          Vandal clones the company into a deterministic twin and tries every short sequence of attacker moves and bank faults against it
          under <span className="num text-ink">{policy}</span>, looking for one that sends money to the wrong place. Nothing here touches
          the live books.
        </>
      }
      actions={
        <Button tone="ghost" onClick={onInject} disabled={!s.ready}>
          Try your own scenario
        </Button>
      }
      next={{
        label: "Diagnose →",
        onClick: goDiagnose,
        ready: !!attack,
        busy: s.diagnosis.phase === "running",
        hint: attack ? "Next: walk the payment's authorization chain and name the link Guard never checked." : "Find a sequence that breaks the books first.",
      }}
    >
      {/* 1 · the strike */}
      <Block
        label="1 · Release Vandal Strike"
        quiet={!!attack && !running}
        aside={
          <span>
            against <span className="num text-ink">{policy}</span>
          </span>
        }
      >
        <div className="flex flex-wrap items-center gap-3 p-3">
          <p className="min-w-0 flex-1 basis-[24rem] text-xs leading-snug text-dim">
            Runs every short attack sequence against a clone of the books and reports only what broke.
          </p>
          <label className="flex items-center gap-1.5 text-[11px] text-dim" title="How many attacker moves or faults per sequence">
            Moves per sequence
            <select
              value={search.depth}
              onChange={(e) => s.setSearch({ depth: Number(e.target.value) })}
              className="num h-8 rounded border border-line bg-raised px-1.5 text-xs"
            >
              {[1, 2, 3, 4]
                .filter((d) => d <= maxDepth)
                .map((d) => (
                <option key={d} value={d}>
                  k={d}
                </option>
              ))}
            </select>
          </label>
          <Button tone="red" onClick={() => s.runSearch()} busy={running} disabled={!s.ready} nudge={!attack} className="h-8 px-4 text-[13px] font-semibold">
            Release Vandal Strike
          </Button>
        </div>
      </Block>

      <HuntPanel quiet={!!attack && !hunting} />

      {/* 2 · what the search found */}
      {(running || r || attack) && (
        <Block
          label={hunted ? "2 · What the hunt found" : "2 · What the search found"}
          aside={
            r && (
              <span className="flex items-center gap-2">
                {r.cached && <Badge tone="warn">recorded</Badge>}
                <span className="num">
                  depth {r.depth} · alphabet {r.alphabet} · {r.deduped} deduped · {r.pruned} pruned · {Math.round(r.runs_per_second)} runs/s
                </span>
                {r.cached && !running && (
                  <button
                    type="button"
                    onClick={() => s.runSearch(true)}
                    className="whitespace-nowrap normal-case tracking-normal text-red underline"
                    title="Playback is on, so this came from a recording of the same search. Run it on the host now instead."
                  >
                    run it live
                  </button>
                )}
              </span>
            )
          }
        >
          <div className="grid grid-cols-3">
            <Stat
              label={
                <span className="flex items-center gap-1.5">
                  {hunted ? "Attempts" : "Sequences tried"} {running && <LiveDot className="text-red" />}
                </span>
              }
              value={explored.toLocaleString()}
              sub={hunted ? "hunt hypotheses, each run on the twin" : running ? `exploring depth ${search.atDepth}…` : r ? `per depth [${r.levels.join(", ")}]` : attack?.source === "inject" ? "around your scenario" : undefined}
            />
            <Stat label="Safe" value={explored ? `${safe.toLocaleString()} / ${explored.toLocaleString()}` : "—"} tone="ok" sub="Guard held, or nothing broke" />
            <Stat
              label="Broke the books"
              value={running && !r ? "…" : broke}
              tone={broke ? "bad" : "ok"}
              sub={broke ? `up to ${usd(Math.max(...(r?.findings.map((f) => f.exposure) ?? [attack?.finding.exposure ?? 0])), { cents: false })} misdirected` : "none within this depth"}
            />
          </div>
          {r && broke === 0 && !running && (
            <p className="border-t border-line px-3 py-2 text-xs text-dim">
              No violation within depth {r.depth} under {policy}. A bounded claim, not a proof beyond it. Try a deeper search or another threat.
            </p>
          )}
        </Block>
      )}

      {/* 3 · the counterexample */}
      {attack && (
        <Reveal k={attack.jobId}>
          <Block
            label="3 · The sequence that broke the books"
            aside={<Badge tone="dim">{attack.source === "inject" ? "from your scenario" : attack.source === "hunt" ? "from the hunt" : "shortest one found"}</Badge>}
          >
            <div className="grid grid-cols-1 gap-px bg-line md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
              <div className="bg-panel p-3">
                <MovesTimeline moves={attack.finding.moves} labels={attack.labels} judge={s.judge} />
              </div>
              <div className="space-y-3 bg-panel p-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-faint">Money misdirected</div>
                  <div className="num text-2xl font-semibold text-bad">{usd(attack.finding.exposure)}</div>
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">Invariants broken</div>
                  <ul className="space-y-0.5">
                    {attack.finding.violated.map((v) => (
                      <li key={v} className="flex gap-2 text-xs">
                        <span className="num shrink-0 text-bad">{v}</span>
                        <span className="text-dim">{INVARIANTS[v]}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                {violations.length > 0 && (
                  <div>
                    <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">On the clone</div>
                    <ul className="space-y-0.5">
                      {violations.slice(0, 3).map((v, i) => (
                        <li key={i} className="num text-[11px] text-dim">
                          {v.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
            {r && r.findings.length > 1 && (
              <details className="border-t border-line px-3 py-2 text-[11px] text-dim">
                <summary className="cursor-pointer">All {r.findings.length} sequences that broke the books</summary>
                <ol className="num mt-1.5 space-y-1">
                  {r.findings.map((f, i) => (
                    <li key={i} className={cx("break-all", sig(f) === sig(attack.finding) ? "text-ink" : "")}>
                      <span className="text-faint">{i + 1}.</span> {f.moves.map(moveLine).join(" → ")} · <span className="text-bad">{usd(f.exposure, { cents: false })}</span> ·{" "}
                      {f.violated.join(" ")}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </Block>
        </Reveal>
      )}

      {/* 4 · the evidence */}
      {attack && before && (
        <Reveal k={s.focusRunId}>
          <div className="mb-1.5 flex items-baseline gap-2 px-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-dim">4 · Evidence</span>
            <span className="text-[11px] text-faint">replayed on a fresh clone, {before.run.run_id}</span>
          </div>
          <EvidenceScan />
        </Reveal>
      )}
    </StagePage>
  );
}
