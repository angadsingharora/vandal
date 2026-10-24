"use client";

import { useState } from "react";
import { parseParams, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Move, OracleLabel } from "@/lib/types";
import { MovesTimeline } from "./SearchPanel";
import { Badge, Button, Modal, Tabs } from "./ui";

const EXAMPLES = [
  "a vendor emails new bank details after approval, then calls to confirm",
  "the CFO calls from an airport asking for an urgent wire to a new supplier",
  "a tenant overpays and asks for a refund to a new account",
  "the bank loses the ack during the payment run",
];

const KINDS: Move["kind"][] = [
  "change_request",
  "inbound_confirmation",
  "submit_invoice",
  "fault",
  "trigger_batch",
  "retry",
  "deposit",
  "refund_request",
  "message",
  "tick",
];

interface Row {
  kind: Move["kind"];
  at: number;
  params: string;
}

// Scenario A by hand (backend/scenarios/a_manual.json).
const SCENARIO_A: Row[] = [
  { kind: "change_request", at: 2, params: "vendor=V-007 fields=bank channel=email sender=lookalike" },
  { kind: "trigger_batch", at: 2, params: "" },
];

export function InjectDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const [mode, setMode] = useState<"plain" | "compose">("plain");
  const [description, setDescription] = useState(EXAMPLES[0]);
  const [rows, setRows] = useState<Row[]>(SCENARIO_A);
  const [labels, setLabels] = useState("");
  const [depth, setDepth] = useState(2);
  const [noLlm, setNoLlm] = useState(() => !(s.settings?.api_key || s.settings?.playback));
  const [formError, setFormError] = useState<string | null>(null);
  const { inject } = s;
  const running = inject.phase === "running";

  const body = () => {
    setFormError(null);
    if (mode === "plain") return { description, depth, no_llm: noLlm };
    const moves: Move[] = rows.map((r) => ({ kind: r.kind, at: r.at, params: parseParams(r.params) }));
    const parsed: OracleLabel[] = labels.trim() ? JSON.parse(labels) : [];
    return { moves, labels: parsed, depth, description: "composed in the war room" };
  };

  const act = async (run: boolean) => {
    let b;
    try {
      b = body();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
      return;
    }
    await (run ? s.runInject(b) : s.previewInject(b));
  };

  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const r = inject.result;

  return (
    <Modal title="Try your own scenario" onClose={onClose} wide>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <Tabs
            value={mode}
            onChange={setMode}
            tabs={[
              { id: "plain", label: "Plain language" },
              { id: "compose", label: "Compose moves" },
            ]}
          />
          {mode === "plain" ? (
            <div className="space-y-2">
              <label htmlFor="threat" className="text-[11px] text-dim">
                Describe a threat against {s.summary?.company ?? "the company"}. Red maps it onto moves the twin can model and reports what it can&apos;t.
              </label>
              <textarea
                id="threat"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                className="w-full rounded border border-line bg-bg p-2 text-sm focus:border-blue focus:outline-none"
              />
              <div className="flex flex-wrap gap-1">
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => setDescription(ex)} className="rounded-sm border border-line px-1.5 py-0.5 text-left text-[11px] text-dim hover:text-ink">
                    {ex}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-1.5 text-[11px] text-dim">
                <input type="checkbox" checked={noLlm} onChange={(e) => setNoLlm(e.target.checked)} className="accent-blue" />
                Read it with keywords instead of Claude
              </label>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-[11px] text-dim">
                Moves land just before World step <span className="num">at</span> (5 steps a day: ops, approvals, batch, bank, tick).
              </div>
              {rows.map((row, i) => (
                <div key={i} className="flex gap-1">
                  <select
                    aria-label="Move kind"
                    value={row.kind}
                    onChange={(e) => setRow(i, { kind: e.target.value as Move["kind"] })}
                    className="h-7 rounded border border-line bg-raised px-1 text-xs"
                  >
                    {KINDS.map((k) => (
                      <option key={k}>{k}</option>
                    ))}
                  </select>
                  <input
                    aria-label="at"
                    type="number"
                    min={0}
                    value={row.at}
                    onChange={(e) => setRow(i, { at: Number(e.target.value) || 0 })}
                    className="num h-7 w-12 rounded border border-line bg-bg px-1 text-xs"
                  />
                  <input
                    aria-label="params"
                    value={row.params}
                    onChange={(e) => setRow(i, { params: e.target.value })}
                    placeholder="key=value …"
                    className="num h-7 min-w-0 flex-1 rounded border border-line bg-bg px-1.5 text-xs"
                  />
                  <button onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))} aria-label="Remove move" className="px-1 text-dim hover:text-bad">
                    ✕
                  </button>
                </div>
              ))}
              <div className="flex gap-1.5">
                <Button tone="ghost" onClick={() => setRows((rs) => [...rs, { kind: "change_request", at: 2, params: "" }])}>
                  + move
                </Button>
                <Button tone="ghost" onClick={() => setRows(SCENARIO_A)}>
                  Scenario A
                </Button>
              </div>
              <label htmlFor="labels" className="block text-[11px] text-dim">
                Answer key (optional JSON list of oracle labels)
              </label>
              <textarea
                id="labels"
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                rows={2}
                placeholder='[{"subject": "MSG-0001", "label": "true_sender", "value": "attacker"}]'
                className="num w-full rounded border border-line bg-bg p-2 text-[11px] focus:border-blue focus:outline-none"
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <label className="flex items-center gap-1 text-[11px] text-dim" htmlFor="inject-depth">
              search
              <select id="inject-depth" value={depth} onChange={(e) => setDepth(Number(e.target.value))} className="num h-7 rounded border border-line bg-raised px-1 text-xs">
                {[0, 1, 2, 3].map((d) => (
                  <option key={d} value={d}>
                    k={d}
                  </option>
                ))}
              </select>
              around it
            </label>
            <Button onClick={() => act(false)} disabled={running}>
              Preview
            </Button>
            <Button tone="red" onClick={() => act(true)} busy={running}>
              Run on {s.summary?.policy ?? "the live policy"}
            </Button>
          </div>
          {formError && <div className="text-[11px] text-bad">{formError}</div>}
        </div>

        <div className="min-w-0 space-y-3 border-line md:border-l md:pl-4">
          {!inject.plan && !r && <div className="text-xs text-faint">Preview shows the moves Red will play. Run plays them on a fresh clone, searches around them, and hands any violation to the loop.</div>}
          {inject.plan && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-dim">Threat plan</span>
                <Badge>{inject.plan.source}</Badge>
                <Badge>scenario {inject.plan.scenario}</Badge>
              </div>
              <MovesTimeline moves={inject.plan.moves} labels={inject.plan.labels} judge={s.judge} />
              {inject.plan.notes.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-[11px] text-warn">
                  {inject.plan.notes.map((n, i) => (
                    <li key={i}>note: {n}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {r && (
            <div className="space-y-2 border-t border-line pt-3">
              <div className="text-xs">
                On a fresh clone:{" "}
                {r.fresh.violated.length ? <span className="text-bad">broke {r.fresh.violated.join(", ")}</span> : <span className="text-ok">no violation by itself</span>}
                {r.explored > 0 && <span className="text-dim"> · searched {r.explored} sequences around it</span>}
              </div>
              {r.best ? (
                <div className="rounded border border-bad/40 bg-bad/10 p-2">
                  <div className="flex items-baseline justify-between text-xs">
                    <span className="text-bad">Counterexample ({r.best.moves.length} moves): {r.best.violated.join(", ")}</span>
                    <span className="num font-bold text-bad">{usd(r.best.exposure)}</span>
                  </div>
                  {!r.needed && <div className="mt-1 text-[11px] text-warn">Search found this without your moves: the injected threat wasn&apos;t needed for it.</div>}
                  <div className="mt-2 flex gap-1.5">
                    <Button
                      tone="red"
                      onClick={() => {
                        onClose();
                        void s.diagnose();
                      }}
                    >
                      Send to diagnose → CEGIS
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="rounded border border-ok/40 bg-ok/10 p-2 text-xs text-ok">Controls held: nothing broke within k={depth} around your threat.</div>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
