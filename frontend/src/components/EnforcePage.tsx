"use client";

// Step 7, Blue. The policy Guard now enforces, then the proof that matters: Red's exact attack
// replayed on a fresh clone under it, before and after, and what Guard did to each action.

import { cx, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { ReplayOut } from "@/lib/types";
import { VerdictFeed } from "./BluePanels";
import { StagePage } from "./Stage";
import { ControlLine, ControlList } from "./synth";
import { Badge, Block, Button, Empty, Reveal } from "./ui";

function Replayed({ title, out, policy }: { title: string; out: ReplayOut | null; policy?: string }) {
  if (!out) {
    return (
      <div className="flex min-h-28 flex-col justify-center bg-panel p-4">
        <div className="text-[10px] uppercase tracking-wider text-faint">{title}</div>
        <div className="text-xs text-faint">not replayed yet{policy ? ` under ${policy}` : ""}</div>
      </div>
    );
  }
  const held = out.result.violations.length === 0;
  return (
    <div className={cx("min-h-28 bg-panel p-4", held ? "bg-ok/[0.06]" : "bg-bad/[0.06]")}>
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wider text-dim">
          {title} · <span className="num">{out.run.policy}</span>
        </span>
        <span className={cx("text-xs font-bold tracking-wider", held ? "text-ok" : "text-bad")}>{held ? "HELD" : "BROKEN"}</span>
      </div>
      <div className={cx("num mt-1 text-2xl font-semibold", held ? "text-ok" : "text-bad")}>{usd(out.result.exposure)}</div>
      <div className="text-[11px] text-dim">
        {held ? "moved to the wrong place: nothing. No invariant broke." : `${out.result.violated.join(", ")} broke`} · payments{" "}
        {Object.entries(out.run.payments)
          .map(([k, v]) => `${v} ${k}`)
          .join(", ")}
      </div>
    </div>
  );
}

export function EnforcePage() {
  const s = useWarRoom();
  const live = s.tabs.find((t) => t.kind === "live");
  const version = s.appliedPolicy ?? live?.policy ?? "v0";
  const info = s.policies.find((p) => p.name === version);
  const synthesized = s.synth.result?.policy?.version === version ? s.synth.result.policy : null;
  const attack = s.attack;
  const { before, after } = s.replays;
  const held = after ? after.result.violations.length === 0 : null;

  return (
    <StagePage
      stage="enforce"
      lede={
        <>
          Guard now enforces <span className="num text-ink">{version}</span> on the live path. The proof that matters is Strike&apos;s exact attack, replayed on a
          fresh clone under the new policy.
        </>
      }
      next={{
        label: `Operate under ${version} →`,
        onClick: () => void s.setStage("operate"),
        ready: true,
        tone: "blue",
        nudge: !!after,
        hint: after
          ? held
            ? `Loop closed. Strike found the gap, built and proved ${version}, and Guard now holds the attack. Keep operating, or attack ${version} next.`
            : `${version} did not hold Strike's attack. Back to Fix: synthesize with a deeper search.`
          : s.appliedPolicy
            ? "Replay the attack first to see the policy hold."
            : "Approve and apply Strike's fix first.",
      }}
    >
      <Block
        label="Enforced policy"
        quiet={!!after}
        aside={
          <>
            {s.appliedPolicy && <Badge tone="ok">applied from Strike</Badge>}
            {live && (
              <span>
                live run <span className="num">{live.id}</span>
              </span>
            )}
          </>
        }
      >
        <div className="flex flex-wrap items-start gap-4 p-3">
          <span className="num text-xl font-semibold text-ink">{version}</span>
          <div className="min-w-0 flex-1 basis-96">
            {synthesized ? (
              <ControlList policy={synthesized} chosen={s.synth.result?.chosen} />
            ) : info && info.controls.length > 0 ? (
              <div className="space-y-1.5">
                {info.controls.map((c) => (
                  <ControlLine key={c} control={c} />
                ))}
              </div>
            ) : (
              <p className="text-xs text-dim">Baseline: no extra controls. Every action still passes Guard&apos;s built-in checks.</p>
            )}
          </div>
        </div>
      </Block>

      {attack ? (
        <Block label="Strike's attack, before and after">
          <div className="grid grid-cols-1 gap-px bg-line md:grid-cols-2">
            <Replayed title="Before" out={before} policy={attack.policy} />
            <Reveal k={after?.run.run_id ?? "none"} className="rounded-none">
              <Replayed title="After" out={after} policy={s.appliedPolicy ?? undefined} />
            </Reveal>
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-line p-3">
            <Button
              tone="blue"
              nudge={!after && !!s.appliedPolicy}
              disabled={!s.appliedPolicy}
              className="h-9 px-4 text-[13px] font-semibold"
              onClick={() => s.appliedPolicy && s.replayAttack(s.appliedPolicy)}
            >
              {after ? "Replay again" : `Replay Strike's attack under ${version}`}
            </Button>
            <span className="text-xs text-dim">
              {!s.appliedPolicy
                ? "Approve and apply Strike's fix first."
                : after
                  ? held
                    ? `Held before execution. ${usd(after.result.exposure)} moved.`
                    : `Still broken under ${after.run.policy}.`
                  : "Same moves, fresh clone, new policy."}
            </span>
          </div>
        </Block>
      ) : (
        <Block label="Strike's attack">
          <Empty>Once Strike finds an attack, its before and after replays show here.</Empty>
        </Block>
      )}

      {after && (
        <Reveal k={after.run.run_id}>
          <div className="mb-1.5 flex items-baseline gap-2 px-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-dim">What Guard did</span>
            <span className="text-[11px] text-faint">every verdict on the replay, {after.run.run_id}</span>
          </div>
          <div className="h-[46vh] overflow-hidden rounded border border-line">
            <VerdictFeed initialFilter={held ? "hold" : "all"} />
          </div>
        </Reveal>
      )}
    </StagePage>
  );
}
