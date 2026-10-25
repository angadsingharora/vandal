"use client";

// Step 6, Blue. The fix from Red, with the rule itself and its evidence, and the two human
// decisions: approve it as the Controller, then apply it to Guard. Payments Guard escalated
// wait below.

import { CONTROLLER, useWarRoom } from "@/lib/store";
import { PaymentApprovals } from "./BluePanels";
import { StagePage } from "./Stage";
import { ControlLine, ControlList, PolicyDiff } from "./synth";
import { Badge, Block, Button, Empty, Reveal } from "./ui";

const STATUS_TONE = { pending: "warn", approved: "blue", applied: "ok", denied: "bad" } as const;

export function ApprovePage() {
  const s = useWarRoom();
  const patch = s.patch;
  const synthesized = patch && s.synth.result?.policy?.version === patch.version ? s.synth.result.policy : null;
  const info = patch ? s.policies.find((p) => p.name === patch.version) : undefined;
  const applied = patch?.status === "applied";

  return (
    <StagePage
      stage="approve"
      lede="A human decides. Red's rule arrives with its evidence pack; the Controller approves or denies it, then applies it to Guard. Payments Guard escalated wait here too."
      actions={
        <button onClick={s.loadApprovals} className="text-[11px] text-dim hover:text-ink">
          refresh
        </button>
      }
      next={{
        label: "Enforce →",
        onClick: () => void s.setStage("enforce"),
        ready: !!s.appliedPolicy,
        tone: "blue",
        hint: s.appliedPolicy ? `Next: replay Red's attack under ${s.appliedPolicy}. Guard should hold it.` : patch ? "Approve and apply the fix first." : "Nothing from Red yet.",
      }}
    >
      {!patch && (
        <Block label="Fix from Red">
          <Empty>Nothing from Red yet. Prove a control on the Red side and send it over.</Empty>
        </Block>
      )}

      {patch && (
        <Reveal k={patch.id + patch.status}>
          <Block
            label={
              <>
                Fix from Red · <span className="num normal-case tracking-normal text-ink">{patch.version}</span>
              </>
            }
            aside={
              <>
                <Badge tone={STATUS_TONE[patch.status]}>{patch.status}</Badge>
                <Badge tone={patch.approvable ? "ok" : "bad"}>{patch.approvable ? "approvable" : "not approvable"}</Badge>
              </>
            }
          >
            <div className="grid grid-cols-1 gap-px bg-line lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <div className="space-y-3 bg-panel p-4">
                <div className="text-[11px] text-dim">
                  submitted by {patch.submitted_by} ({patch.submitter_role}) · evidence pack <span className="num">{patch.evidence ?? "—"}</span>
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">The rule</div>
                  {synthesized ? (
                    <ControlList policy={synthesized} chosen={s.synth.result?.chosen} />
                  ) : info && info.controls.length > 0 ? (
                    <div className="space-y-1.5">
                      {info.controls.map((c) => (
                        <ControlLine key={c} control={c} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-dim">The rule's text is in the evidence pack.</p>
                  )}
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">Evidence</div>
                  <div className="flex flex-wrap gap-1">
                    {patch.checks.map((c) => (
                      <Badge key={c.name} tone={c.passed ? "ok" : "bad"}>
                        {c.passed ? "✓" : "✗"} {c.name}
                      </Badge>
                    ))}
                  </div>
                </div>
                {synthesized && (
                  <details className="text-[11px] text-dim">
                    <summary className="cursor-pointer">
                      Policy diff, {synthesized.parent} → {synthesized.version}
                    </summary>
                    <div className="mt-1">
                      <PolicyDiff policy={synthesized} />
                    </div>
                  </details>
                )}
              </div>

              <div className="flex flex-col justify-center gap-3 bg-panel p-4">
                {patch.status === "pending" && (
                  <>
                    <p className="text-xs leading-snug text-dim">
                      Approve as the Controller. Segregation of duties holds here as everywhere: neither the Operator nor the synthesizer can approve their own
                      change.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button tone="blue" nudge className="h-9 px-4 text-[13px] font-semibold" onClick={() => s.decidePatch(CONTROLLER, true)}>
                        Approve as Controller
                      </Button>
                      <Button className="h-9" onClick={() => s.decidePatch(CONTROLLER, false, "declined in the war room")}>
                        Deny
                      </Button>
                    </div>
                  </>
                )}
                {patch.status === "approved" && (
                  <>
                    <p className="text-xs leading-snug text-dim">
                      Approved by {patch.decided_by}. Applying makes <span className="num text-ink">{patch.version}</span> the policy Guard enforces on the live
                      run from now on.
                    </p>
                    <div>
                      <Button tone="blue" nudge className="h-9 px-4 text-[13px] font-semibold" onClick={s.applyPatch}>
                        Apply {patch.version} to Guard
                      </Button>
                    </div>
                  </>
                )}
                {applied && (
                  <p className="text-sm text-ok">
                    Applied. Guard now enforces <span className="num">{patch.version}</span>.
                  </p>
                )}
                {patch.status === "denied" && (
                  <p className="text-xs text-bad">Denied{patch.decided_by ? ` by ${patch.decided_by}` : ""}. Red can synthesize again.</p>
                )}
              </div>
            </div>
          </Block>
        </Reveal>
      )}

      <Block label="Payments awaiting a human" quiet={!!patch && !applied}>
        <PaymentApprovals />
      </Block>
    </StagePage>
  );
}
