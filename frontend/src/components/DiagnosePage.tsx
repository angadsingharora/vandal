"use client";

// Step 3, Red. The root cause first, then the chain it was found in. The footer starts the
// synthesis and moves to Fix.

import { INVARIANTS, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { ChainView } from "./ChainView";
import { StagePage } from "./Stage";
import { Badge, Block, Button, Empty, Reveal, Spinner } from "./ui";

export function DiagnosePage() {
  const s = useWarRoom();
  const { diagnosis, attack, synth } = s;
  const d = diagnosis.data;
  const running = diagnosis.phase === "running";

  const goFix = () => {
    void s.setStage("fix");
    if (!synth.result?.policy && synth.phase !== "running") void s.synthesize();
  };

  return (
    <StagePage
      stage="diagnose"
      lede="Every payment should carry an unbroken chain: obligation → approval → execution → settlement → books. Diagnosis walks that chain for the misdirected payment and names the first link Guard never checked."
      actions={
        attack && (
          <Button tone="red" onClick={s.diagnose} busy={running} nudge={!d && !running}>
            {d ? "Diagnose again" : "Diagnose"}
          </Button>
        )
      }
      next={{
        label: "Synthesize a control →",
        onClick: goFix,
        ready: !!d,
        busy: synth.phase === "running",
        hint: d
          ? `Next: propose controls for the ${d.gap} gap, let Vandal attack each one, keep the one that survives.`
          : attack
            ? "Name the broken link first."
            : "Find a counterexample on the Attack page first.",
      }}
    >
      {!attack && <Empty>No counterexample yet. Go back to Attack and unleash Vandal.</Empty>}

      {attack && running && (
        <div className="flex items-center gap-2 px-1 text-xs text-dim">
          <Spinner /> walking the chain for the misdirected payment…
        </div>
      )}

      {d && (
        <Reveal k={d.payment + d.gap}>
          <Block
            label="Root cause"
            aside={
              <span className="num" title={d.cites.join(" ")}>
                cites {d.cites.slice(0, 5).join(" ")}
                {d.cites.length > 5 && ` +${d.cites.length - 5}`}
              </span>
            }
          >
            <div className="grid grid-cols-1 gap-px bg-line md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <div className="bg-panel p-4">
                <div className="num text-[11px] uppercase tracking-wider text-bad">
                  {d.gap} · at {d.link}
                </div>
                <p className="mt-1.5 text-[15px] leading-snug text-ink">{d.reason}</p>
                {d.also.length > 0 && <p className="mt-2 text-[11px] text-dim">Also uncovered: {d.also.join(", ")}</p>}
              </div>
              <div className="space-y-3 bg-panel p-4">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-faint">Exposure</div>
                  <div className="num text-xl font-semibold text-bad">{usd(d.exposure)}</div>
                  <div className="num text-[11px] text-dim">{d.payment}</div>
                </div>
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-faint">Invariants broken</div>
                  <ul className="space-y-0.5">
                    {d.violated.map((v) => (
                      <li key={v} className="flex gap-2 text-xs">
                        <Badge tone="bad">{v}</Badge>
                        <span className="text-dim">{INVARIANTS[v]}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </Block>
        </Reveal>
      )}

      {diagnosis.phase === "done" && !d && diagnosis.reason && (
        <Block label="Nothing to diagnose">
          <p className="p-3 text-xs text-dim">{diagnosis.reason}</p>
        </Block>
      )}

      <ChainView />
    </StagePage>
  );
}
