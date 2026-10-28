"use client";

// Step 4, Red. CEGIS: the control that survived, spelled out in full, on top; the candidates it
// beat and their scores below. The footer starts verification and moves to Prove.

import { cx, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { StagePage } from "./Stage";
import { code, ControlList, LogItem, OUTCOME_SHORT, OUTCOME_TONE, params, PolicyDiff } from "./synth";
import { Badge, Block, Button, Empty, LiveDot, Reveal, Table, td } from "./ui";

export function FixPage() {
  const s = useWarRoom();
  const { synth, attack, verify } = s;
  const running = synth.phase === "running";
  const result = synth.result;
  const policy = result?.policy ?? null;
  const scored = [...synth.log].filter((e) => e.score != null).sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
  const best = policy ? result?.log.find((e) => e.outcome === "survived") : undefined;
  const maxDepth = s.settings?.limits?.max_depth ?? 6;
  const canSynth = !!attack && s.diagnosis.phase === "done";

  const goProve = () => {
    void s.setStage("prove");
    if (!verify.pack && verify.phase !== "running") void s.verifyChoice();
  };

  return (
    <StagePage
      stage="fix"
      lede="Counterexample-guided synthesis. Propose a control from the template library, let Vandal attack it, run it against legitimate operations, learn from whatever beat it, repeat. The survivor becomes a new policy version."
      actions={
        <>
          <label className="flex items-center gap-1 text-[11px] text-dim" title="Search depth for attacking each candidate, and for verifying the choice">
            k
            <select value={synth.depth} onChange={(e) => s.setSynthDepth(Number(e.target.value))} className="num h-7 rounded border border-line bg-raised px-1 text-[11px]">
              {[1, 2, 3]
                .filter((d) => d <= maxDepth)
                .map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-[11px] text-dim" title="Sweep the templates' parameters instead of asking Claude for candidates">
            <input type="checkbox" checked={synth.noLlm} onChange={(e) => s.setNoLlm(e.target.checked)} className="accent-blue" />
            no LLM
          </label>
          <Button
            tone="red"
            onClick={s.synthesize}
            busy={running}
            disabled={!canSynth}
            nudge={!policy && !running && canSynth}
            title={!attack ? "Find a counterexample first" : s.diagnosis.phase !== "done" ? "Diagnose first" : ""}
          >
            {result ? "Synthesize again" : "Synthesize a control"}
          </Button>
        </>
      }
      next={{
        label: "Verify →",
        onClick: goProve,
        ready: !!policy,
        busy: verify.phase === "running",
        hint: policy
          ? `Next: prove ${policy.version} holds. Replay, re-search, held-out variants, regression, every seeded invoice, every invariant.`
          : running
            ? `${synth.log.length} candidates tried so far…`
            : canSynth
              ? "Synthesize a control first."
              : "Diagnose the counterexample first.",
      }}
    >
      {policy && result && (
        <Reveal k={policy.version}>
          <Block
            label={
              <>
                The control that survived · <span className="num normal-case tracking-normal text-ink">{policy.version}</span>
              </>
            }
            aside={
              <>
                {result.cached && <Badge tone="warn">recorded</Badge>}
                <Badge tone="ok">{result.status.replaceAll("_", " ")}</Badge>
                <span className="num">
                  {result.iterations} iterations{result.score != null && ` · score ${result.score.toLocaleString()}`}
                </span>
              </>
            }
          >
            <div className="grid grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
              <div className="space-y-3 bg-panel p-3">
                <p className="text-xs leading-snug text-dim">{result.reason}</p>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">
                    {policy.controls.length === 1 ? "The rule" : `The rules, ${result.chosen.map(code).join(" + ")}`}
                  </div>
                  <ControlList policy={policy} chosen={result.chosen} />
                </div>
                {best?.measurement && (
                  <p className="num text-[11px] text-dim">
                    residual exposure {usd(best.measurement.residual_exposure, { cents: false })} · {best.measurement.legit_blocked} legitimate payments blocked ·{" "}
                    {best.measurement.counterexamples} counterexamples left
                  </p>
                )}
              </div>
              <div className="bg-panel p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">
                  Policy diff <span className="num normal-case tracking-normal text-ink">{policy.parent} → {policy.version}</span>
                </div>
                <PolicyDiff policy={policy} />
              </div>
            </div>
          </Block>
        </Reveal>
      )}

      {result && !policy && (
        <Block label={result.status.replaceAll("_", " ")}>
          <p className="p-3 text-xs text-warn">{result.reason}</p>
        </Block>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Block
          label="Candidates tried"
          quiet={!!policy}
          aside={
            <>
              {running && <LiveDot className="text-red" />}
              <span className="num">{synth.log.length}</span>
            </>
          }
        >
          <div className="max-h-[52vh] overflow-auto">
            {synth.log.length === 0 ? (
              <Empty>{running ? "Proposing candidates…" : "Each candidate control is attacked by search and run against legitimate operations."}</Empty>
            ) : (
              <ul>
                {synth.log.map((e, i) => (
                  <LogItem key={i} e={e} />
                ))}
              </ul>
            )}
          </div>
        </Block>

        <Block label="Scored" quiet={!!policy} aside={<span>lower is better</span>}>
          <div className="max-h-[52vh] overflow-auto">
            {scored.length === 0 ? (
              <Empty>Scores appear as candidates are measured.</Empty>
            ) : (
              <Table head={["Candidate", "Outcome", "Residual", "Blocked", "Score"]}>
                {scored.map((e, i) => (
                  <tr key={i} className={cx(e === best && "bg-ok/10")}>
                    <td className={cx(td, "num")} title={[...e.base, e.candidate].join("\n+ ")}>
                      <div>{[...e.base, e.candidate].map(code).join(" + ")}</div>
                      <div className="max-w-[16rem] truncate text-[10px] text-faint">{params(e.candidate)}</div>
                    </td>
                    <td className={cx(td, "whitespace-nowrap")}>
                      <Badge tone={OUTCOME_TONE[e.outcome] ?? "dim"}>{OUTCOME_SHORT[e.outcome] ?? e.outcome}</Badge>
                    </td>
                    <td className={cx(td, "num text-right")}>{e.measurement ? usd(e.measurement.residual_exposure, { cents: false }) : "—"}</td>
                    <td className={cx(td, "num text-right")}>{e.measurement?.legit_blocked ?? "—"}</td>
                    <td className={cx(td, "num text-right")}>{e.score?.toLocaleString()}</td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </Block>
      </div>
    </StagePage>
  );
}
