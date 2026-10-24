"use client";

import { cx, moveLine, pct, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { LogEntry, Scorecard } from "@/lib/types";
import { Badge, Button, Empty, LiveDot, Panel, SideTag, Table, td } from "./ui";

/** What each verification check proves (DESIGN 10), for the tooltip on its name. */
const CHECK_HELP: Record<string, string> = {
  replay: "The minimal counterexample, replayed under the new policy, is held or blocked",
  "re-search": "The whole bounded search space under the new policy finds no violation within k",
  variants: "Held-out Red content (other vendors, amounts, channels, deepfake confirmations) the synthesizer never saw",
  regression: "About 25 legitimate cases, including a real bank change verified by callback, all still complete",
  "legit ops": "All 80 seeded invoices replayed: holds and blocks on legitimate payments",
  invariants: "Every invariant holds in every legitimate run",
};

const OUTCOME_TONE: Record<string, "ok" | "bad" | "warn" | "dim"> = {
  survived: "ok",
  counterexample: "bad",
  false_positive: "warn",
  lint: "dim",
};

function short(control: string): string {
  return control.replace(/\(.*\)$/, "");
}

/** "T2 ApprovalBinding(...)" → "T2". */
function code(control: string): string {
  return control.split(" ")[0];
}

function params(control: string): string {
  return control.match(/\((.*)\)$/)?.[1] ?? "";
}

/** Short outcome names for the narrow candidate table. */
const OUTCOME_SHORT: Record<string, string> = {
  survived: "survived",
  counterexample: "attacked",
  false_positive: "blocks legit",
  lint: "lint",
};

function LogItem({ e }: { e: LogEntry }) {
  return (
    <li className="border-b border-line/50 px-3 py-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span className="num text-faint">it{e.iteration}</span>
        <span className="num font-medium text-ink">{short(e.candidate)}</span>
        <Badge tone={OUTCOME_TONE[e.outcome] ?? "dim"}>{e.outcome.replace("_", " ")}</Badge>
        <span className="ml-auto text-[10px] text-faint">{e.source}</span>
      </div>
      <div className="num truncate text-[11px] text-dim" title={e.candidate}>
        {params(e.candidate)}
      </div>
      <div className="text-[11px] text-dim">{e.detail}</div>
      {e.counterexample && (
        <div className="num mt-0.5 break-all text-[11px] text-bad">↳ {e.counterexample.map(moveLine).join(" → ")}</div>
      )}
      {e.lint.length > 0 && <div className="text-[11px] text-warn">lint: {e.lint.join("; ")}</div>}
    </li>
  );
}

function ScoreRow({ label, before, after, fmt, better }: { label: string; before?: number; after?: number; fmt: (n: number) => string; better: "lower" | "higher" }) {
  const improved = before != null && after != null && (better === "lower" ? after < before : after > before);
  return (
    <tr>
      <td className={cx(td, "text-dim")}>{label}</td>
      <td className={cx(td, "num text-right")}>{before == null ? "—" : fmt(before)}</td>
      <td className={cx(td, "num text-right", improved && "text-ok")}>{after == null ? "—" : fmt(after)}</td>
    </tr>
  );
}

export function ScoreCompare({ before, after }: { before?: Scorecard; after?: Scorecard }) {
  return (
    <Table head={["", before?.policy ?? "before", after?.policy ?? "after"]}>
      <ScoreRow label="Attack success" before={before?.attack_success_rate} after={after?.attack_success_rate} fmt={(n) => pct(n)} better="lower" />
      <ScoreRow label="Exposure" before={before?.exposure} after={after?.exposure} fmt={(n) => usd(n, { cents: false })} better="lower" />
      <ScoreRow label="Violations found" before={before?.violations_found} after={after?.violations_found} fmt={String} better="lower" />
      <ScoreRow label="Legit blocked" before={before?.legit_blocked} after={after?.legit_blocked} fmt={String} better="lower" />
      <ScoreRow label="False positives" before={before?.false_positive_rate} after={after?.false_positive_rate} fmt={(n) => pct(n, 1)} better="lower" />
      <ScoreRow label="Holds (friction)" before={before?.holds} after={after?.holds} fmt={String} better="lower" />
    </Table>
  );
}

export function SynthesisPanel() {
  const s = useWarRoom();
  const { synth, verify, patch, attack } = s;
  const sendToBlue = async () => {
    await s.submitPatch();
    if (useWarRoom.getState().patch) await s.setView("blue");
  };
  const running = synth.phase === "running";
  const result = synth.result;
  const scored = [...synth.log].filter((e) => e.score != null).sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
  const best = result?.chosen.length ? result.log.find((e) => e.outcome === "survived") : undefined;
  const pack = verify.pack;

  return (
    <Panel
      title={
        <span title="Counterexample-guided inductive synthesis: propose a control from the template library, let search attack it, learn from what beat it, repeat">
          Fix &amp; prove · CEGIS
        </span>
      }
      tag={<SideTag side="red" />}
      actions={
        <>
          <label className="flex items-center gap-1 text-[11px] text-dim" title="Search depth for attacking each candidate, and for verifying the choice">
            k
            <select
              value={synth.depth}
              onChange={(e) => s.setSynthDepth(Number(e.target.value))}
              className="num h-6 rounded border border-line bg-raised px-1 text-[11px]"
            >
              {[1, 2, 3].map((d) => (
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
          <Button tone="red" onClick={s.synthesize} busy={running} disabled={!attack || s.diagnosis.phase !== "done"} title={!attack ? "Find a counterexample first" : s.diagnosis.phase !== "done" ? "Diagnose first" : ""}>
            Synthesize a control
          </Button>
        </>
      }
      bodyClass="grid grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.2fr)] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden"
    >
      <div className="min-h-0 overflow-auto border-b border-line lg:border-b-0 lg:border-r">
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-panel px-3 py-1 text-[10px] uppercase tracking-wider text-faint">
          Iteration log {running && <LiveDot className="text-red" />}
          <span className="num ml-auto">{synth.log.length} candidates</span>
        </div>
        {synth.log.length === 0 ? (
          <Empty>{running ? "Proposing candidates…" : "Each candidate control is attacked by search and run against legitimate operations."}</Empty>
        ) : (
          <ul>{synth.log.map((e, i) => <LogItem key={i} e={e} />)}</ul>
        )}
        {result && (
          <div className={cx("m-3 rounded border p-2 text-xs", result.status === "repaired" ? "border-ok/40 text-ok" : "border-warn/40 text-warn")}>
            <span className="font-semibold">{result.status.replaceAll("_", " ")}</span>: <span className="text-dim">{result.reason}</span>
          </div>
        )}
      </div>

      <div className="min-h-0 overflow-auto border-b border-line lg:border-b-0 lg:border-r">
        <div className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1 text-[10px] uppercase tracking-wider text-faint">
          Scored candidates <span className="normal-case tracking-normal">· lower is better</span>
        </div>
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

      <div className="min-h-0 space-y-3 overflow-auto p-3">
        {!result?.policy && <Empty>The chosen control, its diff, and its proof show up here.</Empty>}
        {result?.policy && (
          <>
            <div>
              <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-faint">
                Policy diff <span className="num normal-case tracking-normal text-ink">{result.policy.parent} → {result.policy.version}</span>
              </div>
              <pre className="num overflow-x-auto rounded border border-line bg-bg p-2 text-[11px] leading-relaxed">
                {result.policy.diff.map((line, i) => (
                  <div key={i} className={line.startsWith("+") ? "text-ok" : line.startsWith("-") ? "text-bad" : "text-dim"}>
                    {line}
                  </div>
                ))}
              </pre>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              <Button tone="red" onClick={s.verifyChoice} busy={verify.phase === "running"} disabled={!synth.jobId}>
                Verify
              </Button>
              <Button tone="blue" onClick={sendToBlue} disabled={verify.phase !== "done" || !!patch} title="Put the verified policy and its evidence pack in Blue's approvals inbox">
                Send to Blue for approval →
              </Button>
              {patch && (
                <span className="text-[11px] text-dim">
                  {patch.id}: <span className="text-ink">{patch.status}</span>
                  {patch.status === "pending" && (
                    <>
                      {" · "}
                      <button onClick={() => void s.setView("blue")} className="text-blue hover:underline">
                        approve it in Blue
                      </button>
                    </>
                  )}
                </span>
              )}
            </div>

            {(verify.checks.length > 0 || verify.phase === "running") && (
              <div>
                <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-faint">
                  Verification {verify.phase === "running" && <LiveDot className="text-blue" />}
                  {pack && <Badge tone={pack.approvable ? "ok" : "bad"}>{pack.approvable ? "approvable" : "not approvable"}</Badge>}
                </div>
                <ul className="space-y-0.5">
                  {verify.checks.map((c) => (
                    <li key={c.number} className="flex gap-2 text-[11px]">
                      <span className={c.passed ? "text-ok" : "text-bad"}>{c.passed ? "✓" : "✗"}</span>
                      <span className="w-20 shrink-0 text-ink" title={CHECK_HELP[c.name]}>
                        {c.name}
                      </span>
                      <span className="text-dim">{c.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {pack && pack.metrics.before && <ScoreCompare before={pack.metrics.before} after={pack.metrics.after} />}

          </>
        )}
      </div>
    </Panel>
  );
}
