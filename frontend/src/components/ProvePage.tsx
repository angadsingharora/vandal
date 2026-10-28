"use client";

// Step 5, Red. The verdict on the chosen control first, then the six checks that produced it,
// then the before/after scorecard. The footer hands the evidence pack to Blue.

import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { StagePage } from "./Stage";
import { CHECK_HELP, ControlList, ScoreCompare } from "./synth";
import { Badge, Block, Button, Empty, LiveDot, Reveal } from "./ui";

export function ProvePage() {
  const s = useWarRoom();
  const { verify, synth, patch } = s;
  const pack = verify.pack;
  const running = verify.phase === "running";
  const policy = synth.result?.policy ?? null;
  const passed = verify.checks.filter((c) => c.passed).length;
  const evidence = pack && verify.jobId ? s.api?.evidenceUrl(verify.jobId) : null;

  return (
    <StagePage
      stage="prove"
      lede="Six checks, all from runs: the counterexample replayed under the new policy, the whole bounded search again, held-out variants the synthesizer never saw, legitimate cases, every seeded invoice, every invariant. Only an approvable pack can cross to Guard."
      actions={
        <Button tone="red" onClick={s.verifyChoice} busy={running} disabled={!synth.jobId || !policy} nudge={!pack && !running && !!policy}>
          {pack ? "Verify again" : "Verify"}
        </Button>
      }
      next={
        patch
          ? {
              label: "Open it in Guard →",
              onClick: () => void s.setStage("approve"),
              ready: true,
              tone: "blue",
              hint: `${patch.id} is ${patch.status} in Guard's inbox.`,
              nudge: patch.status !== "applied",
            }
          : {
              label: "Send to Guard for approval →",
              onClick: () => void s.submitPatch(),
              ready: !!pack?.approvable,
              tone: "blue",
              nudge: !!pack?.approvable,
              hint: pack
                ? pack.approvable
                  ? `Next: ${pack.version} and its evidence pack land in Guard's inbox for the Controller.`
                  : "Not approvable: a check failed. Synthesize again, or deepen the search."
                : policy
                  ? "Verify the control first."
                  : "Synthesize a control first.",
            }
      }
    >
      {!policy && <Empty>No control to prove yet. Synthesize one on the Fix page.</Empty>}

      {pack && (
        <Reveal k={pack.version + String(pack.approvable)}>
          <div className={cx("flex flex-wrap items-center gap-x-4 gap-y-1 rounded border px-4 py-3", pack.approvable ? "border-ok/40 bg-ok/[0.08]" : "border-bad/40 bg-bad/[0.08]")}>
            <span className={cx("text-sm font-semibold", pack.approvable ? "text-ok" : "text-bad")}>
              {pack.version} is {pack.approvable ? "approvable" : "not approvable"}
            </span>
            <span className="num text-xs text-dim">
              {passed}/{verify.checks.length} checks passed
            </span>
            <span className="text-xs text-dim">{pack.approvable ? "The evidence pack travels with the rule." : "A failed check keeps it out of Guard's inbox."}</span>
            {pack.cached && <Badge tone="warn">recorded</Badge>}
            {evidence && (
              <a href={evidence} download className="ml-auto text-xs text-ink underline" title="The pack as JSON: every check, the scorecard before and after, and the rule itself">
                Download evidence pack
              </a>
            )}
          </div>
        </Reveal>
      )}

      {policy && (
        <Block label="Checks" aside={running && <LiveDot className="text-red" />}>
          {verify.checks.length === 0 ? (
            <Empty>{running ? "Running the checks…" : "Verify the chosen control to run the six checks."}</Empty>
          ) : (
            <ol className="divide-y divide-line/60">
              {verify.checks.map((c) => (
                <Reveal key={c.number} k={c.number}>
                  <li className="grid grid-cols-[1.25rem_10rem_minmax(0,1fr)] gap-3 px-3 py-2 text-xs">
                    <span className={cx("text-sm font-bold leading-none", c.passed ? "text-ok" : "text-bad")}>{c.passed ? "✓" : "✗"}</span>
                    <div>
                      <div className="text-ink">
                        <span className="num text-faint">{c.number}.</span> {c.name}
                      </div>
                      <div className="text-[11px] leading-snug text-faint">{CHECK_HELP[c.name]}</div>
                    </div>
                    <div className="num text-dim">{c.detail}</div>
                  </li>
                </Reveal>
              ))}
            </ol>
          )}
        </Block>
      )}

      {pack?.metrics.before && (
        <Block label="Scorecard · before and after">
          <ScoreCompare before={pack.metrics.before} after={pack.metrics.after} />
        </Block>
      )}

      {policy && (
        <Block label={`What ${policy.version} says`} quiet={!!pack}>
          <div className="p-3">
            <ControlList policy={policy} chosen={synth.result?.chosen} />
          </div>
        </Block>
      )}
    </StagePage>
  );
}
