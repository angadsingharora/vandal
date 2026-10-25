"use client";

import { useState } from "react";
import { cx, parseParams, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Move, OracleLabel } from "@/lib/types";
import { MovesTimeline } from "./SearchPanel";
import { Badge, Button, Empty, Modal, Tabs } from "./ui";

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

const FIELD = "h-7 rounded border border-ink/20 bg-bg px-1.5 text-[12px]";
const AREA = "w-full rounded border border-ink/20 bg-bg p-2 text-[12.5px] focus:outline-none focus:border-ink/50";
const LABEL = "text-[11.5px] text-dim";

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
    <Modal title="Try your own scenario" onClose={onClose}>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-4">
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
              <label htmlFor="threat" className={cx(LABEL, "block")} title="Red maps it onto moves the twin can model and reports what it cannot.">
                Describe a threat against {s.summary?.company ?? "the company"}
              </label>
              <textarea id="threat" value={description} onChange={(e) => setDescription(e.target.value)} rows={4} className={AREA} />
              <div className="flex flex-col items-start gap-0.5">
                {EXAMPLES.map((ex) => (
                  <button key={ex} onClick={() => setDescription(ex)} className="text-left text-[11px] text-dim hover:text-ink">
                    {ex}
                  </button>
                ))}
              </div>
              <label className={cx(LABEL, "flex items-center gap-1.5")}>
                <input type="checkbox" checked={noLlm} onChange={(e) => setNoLlm(e.target.checked)} className="accent-red" />
                Read it with keywords instead of Claude
              </label>
            </div>
          ) : (
            <div className="space-y-2">
              <div className={LABEL} title="Five steps a day: ops, approvals, batch, bank, tick.">
                Each move lands just before World step <span className="num">at</span>
              </div>
              {rows.map((row, i) => (
                <div key={i} className="flex gap-1.5">
                  <select aria-label="Move kind" value={row.kind} onChange={(e) => setRow(i, { kind: e.target.value as Move["kind"] })} className={FIELD}>
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
                    className={cx(FIELD, "num w-14")}
                  />
                  <input
                    aria-label="params"
                    value={row.params}
                    onChange={(e) => setRow(i, { params: e.target.value })}
                    placeholder="key=value"
                    className={cx(FIELD, "num min-w-0 flex-1")}
                  />
                  <button onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))} aria-label="Remove move" className="px-1 text-dim hover:text-ink">
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
              <label htmlFor="labels" className={cx(LABEL, "block")} title="Optional JSON list of oracle labels.">
                Answer key
              </label>
              <textarea
                id="labels"
                value={labels}
                onChange={(e) => setLabels(e.target.value)}
                rows={2}
                placeholder='[{"subject": "MSG-0001", "label": "true_sender", "value": "attacker"}]'
                className={cx(AREA, "num")}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <label className={cx(LABEL, "flex items-center gap-1")} htmlFor="inject-depth">
              Search
              <select id="inject-depth" value={depth} onChange={(e) => setDepth(Number(e.target.value))} className={cx(FIELD, "num")}>
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
          {formError && <div className="text-[12px] text-red">{formError}</div>}
        </div>

        <div className="min-w-0 space-y-4 border-line md:border-l md:pl-5">
          {!inject.plan && !r && <Empty>Preview shows the moves Red will play; Run plays them on a fresh clone and searches around them.</Empty>}
          {inject.plan && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[14px] font-medium text-ink">Threat plan</span>
                <Badge>{inject.plan.source}</Badge>
                <Badge className="num">scenario {inject.plan.scenario}</Badge>
              </div>
              <MovesTimeline moves={inject.plan.moves} labels={inject.plan.labels} judge={s.judge} />
              {inject.plan.notes.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-[11px] text-warn">
                  {inject.plan.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {r && (
            <div className="space-y-3 border-t border-line pt-3">
              <div className="text-[12.5px]">
                On a fresh clone:{" "}
                {r.fresh.violated.length ? <span className="text-red">broke {r.fresh.violated.join(", ")}</span> : <span className="text-blue">no violation by itself</span>}
                {r.explored > 0 && (
                  <span className="text-dim">
                    , and searched <span className="num">{r.explored}</span> sequences around it
                  </span>
                )}
              </div>
              {r.best ? (
                <div className="border-l-2 border-red pl-3">
                  <div className="text-[11px] text-dim">
                    Counterexample, <span className="num">{r.best.moves.length}</span> moves
                  </div>
                  <div className="num text-[17px] font-semibold leading-tight text-red">{usd(r.best.exposure)}</div>
                  <div className="text-[12.5px] text-red">{r.best.violated.join(", ")}</div>
                  {!r.needed && <div className="mt-1 text-[11px] text-warn">Found without your moves; the injected threat was not needed.</div>}
                  <div className="mt-2">
                    <Button
                      tone="red"
                      onClick={() => {
                        onClose();
                        void s.diagnose();
                      }}
                    >
                      Diagnose it
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="border-l-2 border-blue pl-3 text-[12.5px] text-blue">
                  Controls held: nothing broke within k=<span className="num">{depth}</span> around your threat.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
