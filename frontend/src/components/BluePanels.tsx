"use client";

import { useMemo, useState } from "react";
import { cx, usd } from "@/lib/format";
import { CFO, CONTROLLER, OPERATOR, useWarRoom } from "@/lib/store";
import type { Decision, ReplayOut, VerdictItem } from "@/lib/types";
import { IntakePanel } from "./IntakePanel";
import { Badge, Button, DecisionBadge, Empty, LiveDot, Panel, Verdict } from "./ui";

function argsLine(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v != null && v !== "" && typeof v !== "object")
    .slice(0, 4)
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
}

const FIELD = "h-7 rounded border border-ink/20 bg-bg px-1.5 text-[12px]";

/** Blue's page controls: which agent a new run gets, and how many days it works. */
export function RunOperations() {
  const s = useWarRoom();
  const [days, setDays] = useState(5);
  const operating = s.operate.phase === "running";
  return (
    <>
      <label className="sr-only" htmlFor="operator">
        Operator
      </label>
      <select
        id="operator"
        value={s.operator}
        onChange={(e) => s.setOperator(e.target.value as "reference" | "llm")}
        className={FIELD}
        title="The agent Guard protects: the deterministic reference Operator, or the LLM Operator that reads messy documents (O1). Takes effect on Reset demo."
      >
        <option value="reference">Reference Operator</option>
        <option value="llm">LLM Operator</option>
      </select>
      <label className="sr-only" htmlFor="days">
        Business days
      </label>
      <input
        id="days"
        type="number"
        min={1}
        max={30}
        value={days}
        onChange={(e) => setDays(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
        className={cx("num w-12", FIELD)}
        title="Business days to operate"
      />
      <Button tone="blue" onClick={() => s.operateDays(days)} busy={operating} disabled={!s.ready}>
        Run operations
      </Button>
      {operating && s.operate.day != null && (
        <span className="num text-[11px] text-dim">
          day {s.operate.day}, {s.operate.events} events
        </span>
      )}
    </>
  );
}

export function OperatorPanel() {
  const s = useWarRoom();
  const cases = s.entities?.cases ?? [];
  const activity = useMemo(() => s.activity.filter((e) => e.actor.startsWith("OP")).slice(-40).reverse(), [s.activity]);
  const open = cases.filter((c) => c.status === "open").length;
  return (
    <Panel
      title="Operator"
      actions={
        <span className="flex items-center gap-2 text-[11px] text-dim">
          {s.summary?.operator === "llm" && <Badge tone="esc">LLM Operator</Badge>}
          {open > 0 && <span className="num">{open} open cases</span>}
        </span>
      }
      className="min-h-[150px]"
    >
      {cases.length > 0 && (
        <ul className="border-b border-line">
          {cases.map((c) => (
            <li key={c.id} className="flex items-center gap-2 border-b border-line px-3 py-1.5 text-[12px] last:border-b-0">
              <Badge tone={c.kind === "recovery" ? "esc" : c.kind === "escalation" ? "warn" : "dim"} className="w-16 shrink-0">
                {c.kind}
              </Badge>
              <span className="min-w-0 flex-1 truncate" title={c.rationale || undefined}>
                <span className="num">{c.subject}</span> <span className="text-dim">{c.reason}</span>
              </span>
              <Badge tone={c.status === "open" ? "warn" : "ok"}>{c.status}</Badge>
            </li>
          ))}
        </ul>
      )}
      {s.summary?.operator === "llm" && <IntakePanel />}
      {activity.length === 0 && cases.length === 0 && s.summary?.operator !== "llm" && (
        <Empty>Run operations to watch the Operator pay invoices.</Empty>
      )}
      <ul>
        {activity.map((e) => (
          <li key={e.id} className="num flex gap-2 border-b border-line px-3 py-1 text-[12px]">
            <span className="w-7 shrink-0 text-dim">d{e.day}</span>
            <span className="shrink-0 text-ink">{e.kind}</span>
            <span className="truncate text-dim">{argsLine(e.payload)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function VerdictRow({ v }: { v: VerdictItem }) {
  const [open, setOpen] = useState(false);
  const chain = Object.entries(v.chain);
  return (
    <li className="border-b border-line">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-start gap-2 px-3 py-1.5 text-left hover:bg-raised">
        <span className="w-14 shrink-0 pt-px">
          <DecisionBadge decision={v.decision} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5 text-[12px]">
            <span className="text-ink">{v.tool}</span>
            <span className="text-[11px] text-dim">{v.stage}</span>
            <span className="num ml-auto text-[11px] text-dim">
              d{v.day} #{v.seq}
            </span>
          </div>
          <div className="num truncate text-[11px] text-dim">
            {v.actor} {argsLine(v.args)}
          </div>
          {v.fired.length > 0 && <div className="num truncate text-[11px] text-warn">fired {v.fired.join(", ")}</div>}
          {v.requires.length > 0 && <div className="truncate text-[11px] text-dim">requires {v.requires.join(", ")}</div>}
        </div>
      </button>
      {open && (
        <div className="num space-y-0.5 px-3 pb-2 pl-[76px] text-[11px] text-dim">
          {v.cites.length > 0 && <div className="break-words">cites {v.cites.join(" ")}</div>}
          {v.cleared_by.length > 0 && <div className="break-words text-blue">cleared by {v.cleared_by.join(" ")}</div>}
          {chain.map(([k, val]) => (
            <div key={k} className="break-all">
              {k}: {typeof val === "object" ? JSON.stringify(val) : String(val)}
            </div>
          ))}
          <div className="break-all">event {v.event}</div>
        </div>
      )}
    </li>
  );
}

const FILTERS: (Decision | "all")[] = ["all", "allow", "hold", "escalate", "block"];

export function VerdictFeed() {
  const s = useWarRoom();
  const [filter, setFilter] = useState<Decision | "all">("all");
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: s.verdicts.length };
    for (const v of s.verdicts) c[v.decision] = (c[v.decision] ?? 0) + 1;
    return c;
  }, [s.verdicts]);
  const rows = useMemo(() => s.verdicts.filter((v) => filter === "all" || v.decision === filter).slice(-150).reverse(), [s.verdicts, filter]);
  const alerts = s.alerts.slice(-5).reverse();

  return (
    <Panel
      title="Verdicts"
      actions={s.operate.phase === "running" && <LiveDot className="text-blue" />}
      className="min-h-[240px]"
      bodyClass="flex flex-col"
    >
      <div className="flex shrink-0 flex-wrap gap-x-3 border-b border-line px-3">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={cx(
              "-mb-px flex items-baseline gap-1 border-b-2 py-1.5 text-[12px]",
              filter === f ? "border-ink font-medium text-ink" : "border-transparent text-dim hover:text-ink",
            )}
          >
            {f} <span className="num font-normal">{counts[f] ?? 0}</span>
          </button>
        ))}
      </div>
      {alerts.length > 0 && (
        <ul className="shrink-0 border-b border-line">
          {alerts.map((a) => (
            <li key={a.seq} className="num break-words border-l-2 border-red px-3 py-1 text-[11px] text-red">
              d{a.day} {String(a.invariant ?? a.kind ?? "")} {String(a.message ?? "")}
            </li>
          ))}
        </ul>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <Empty>Guard's verdicts on each Operator action appear here.</Empty>
        ) : (
          <ul>
            {rows.map((v) => (
              <VerdictRow key={v.seq} v={v} />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

const PATCH_TONE = { applied: "blue", approved: "blue", denied: "red", pending: "warn" } as const;

export function ApprovalsInbox() {
  const s = useWarRoom();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const payments = s.approvals.payments;
  // One row per policy version, the newest: a second loop in the same server resubmits
  // v1-synth, and the older applied patch would only repeat it.
  const patches = useMemo(() => {
    const seen = new Set<string>();
    return [...s.approvals.patches].reverse().filter((p) => !seen.has(p.version) && seen.add(p.version));
  }, [s.approvals.patches]);

  const decide = async (runId: string, id: string, who: typeof CONTROLLER, approve: boolean) => {
    const msg = await s.decidePayment(runId, id, who, approve);
    setNotes((n) => ({ ...n, [id]: msg }));
  };

  return (
    <Panel
      title="Approvals"
      actions={
        <Button tone="ghost" onClick={s.loadApprovals}>
          Refresh
        </Button>
      }
      className="min-h-[160px]"
    >
      {payments.length === 0 && patches.length === 0 && <Empty>Nothing waiting.</Empty>}
      <ul>
        {patches.map((p) => (
          <li key={p.id} className="border-b border-line px-3 py-2">
            <div className="flex items-center gap-2 text-[12.5px]">
              <span className="font-medium text-ink">Fix from Red</span>
              <span className="num">{p.version}</span>
              <Verdict tone={PATCH_TONE[p.status as keyof typeof PATCH_TONE] ?? "dim"} land={p.status !== "pending"} className="ml-auto">
                {p.status}
              </Verdict>
            </div>
            <div className="mt-0.5 text-[11px] text-dim">
              From {p.submitted_by} ({p.submitter_role}), evidence pack {p.evidence ?? "none"}, {p.approvable ? "approvable" : "not approvable"}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
              {p.checks.map((c) => (
                <Badge key={c.name} tone={c.passed ? "ok" : "bad"} title={c.passed ? "Passed" : "Failed"}>
                  {c.name}
                </Badge>
              ))}
            </div>
            {p.decided_by && <div className="mt-0.5 text-[11px] text-dim">Decided by {p.decided_by}</div>}
            {((p.status === "pending" || p.status === "approved") && s.patch?.id === p.id) && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {p.status === "pending" && (
                  <>
                    <Button tone="blue" onClick={() => s.decidePatch(CONTROLLER, true)}>
                      Approve as Controller
                    </Button>
                    <Button onClick={() => s.decidePatch(CONTROLLER, false, "declined in the war room")}>Deny</Button>
                  </>
                )}
                {p.status === "approved" && (
                  <Button tone="blue" onClick={s.applyPatch}>
                    Apply {p.version} to Guard
                  </Button>
                )}
              </div>
            )}
          </li>
        ))}
        {payments.map((p) => (
          <li key={`${p.run_id}-${p.id}`} className="border-b border-line px-3 py-2">
            <div className="flex items-center gap-2 text-[12.5px]">
              <span className="font-medium text-ink">Payment</span>
              <span className="num">{p.invoice}</span>
              <span className="num ml-auto font-medium text-ink">{usd(p.amount)}</span>
            </div>
            <div className="num mt-0.5 text-[11px] text-dim">
              To {p.payee_account}, asked by {p.requested_by}, {p.id}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Button tone="blue" onClick={() => decide(p.run_id, p.id, CONTROLLER, true)}>
                Approve as Controller
              </Button>
              <Button onClick={() => decide(p.run_id, p.id, CFO, false)}>Deny as CFO</Button>
              <Button tone="ghost" onClick={() => decide(p.run_id, p.id, OPERATOR, true)} title="Segregation of duties: Blue should refuse">
                Operator tries to approve
              </Button>
            </div>
            {notes[p.id] && <div className="mt-1 text-[11px] text-warn">{notes[p.id]}</div>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Replayed({
  title,
  out,
  policy,
  land,
  className,
}: {
  title: string;
  out: ReplayOut | null;
  policy?: string;
  land?: boolean;
  className?: string;
}) {
  if (!out) {
    return (
      <div className={cx("min-w-0 flex-1 text-dim", className)}>
        <div className="text-[11px]">
          {title}
          {policy && (
            <>
              , <span className="num">{policy}</span>
            </>
          )}
        </div>
        <div className="text-[12px]">Not replayed yet</div>
      </div>
    );
  }
  const held = out.result.violations.length === 0;
  const payments = Object.entries(out.run.payments)
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");
  const outcome = held ? "No invariant broke" : out.result.violated.join(", ");
  return (
    <div className={cx("min-w-0 flex-1", className)}>
      <div className="text-[11px] text-dim">
        {title}, <span className="num">{out.run.policy}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className={cx("num text-[17px] font-semibold leading-tight", held ? "text-blue" : "text-red")}>{usd(out.result.exposure)}</span>
        <Verdict tone={held ? "blue" : "red"} land={land}>
          {held ? "held" : "broken"}
        </Verdict>
      </div>
      <div className="flex gap-3 text-[11px] text-dim" title={`${outcome}. Payments ${payments}`}>
        <span className="num truncate">{outcome}</span>
        <span className="num truncate">payments {payments}</span>
      </div>
    </div>
  );
}

/** What Guard enforces on the live run, and the proof that a fix from Red works: Red's attack,
 * replayed before and after the policy changed. */
export function EnforcedPolicy() {
  const s = useWarRoom();
  const live = s.tabs.find((t) => t.kind === "live");
  const version = s.appliedPolicy ?? live?.policy ?? "v0";
  const info = s.policies.find((p) => p.name === version);
  const attack = s.attack;
  return (
    <Panel title="Policy" className="h-auto" bodyClass="overflow-visible">
      <div className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="num text-[14px] font-semibold text-ink">{version}</span>
          {s.appliedPolicy && (
            <Verdict tone="blue" land title="Applied from Red">
              applied
            </Verdict>
          )}
        </div>
        {info?.controls.length ? (
          <ul className="num text-[11px] text-dim">
            {info.controls.map((c) => (
              <li key={c} className="truncate" title={c}>
                {c}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-[11px] text-dim">No extra controls</div>
        )}
        {attack ? (
          <>
            <div className="flex">
              <Replayed title="Before" out={s.replays.before} policy={attack.policy} className="pr-3" />
              <Replayed title="After" out={s.replays.after} policy={s.appliedPolicy ?? undefined} land className="border-l border-line pl-3" />
            </div>
            <Button
              tone="blue"
              disabled={!s.appliedPolicy}
              onClick={() => s.appliedPolicy && s.replayAttack(s.appliedPolicy)}
              title={!s.appliedPolicy ? "Approve and apply Red's fix first" : "Run Red's counterexample on a fresh clone under the new policy"}
            >
              Replay Red&apos;s attack under {s.appliedPolicy ?? "the new policy"}
            </Button>
          </>
        ) : (
          <p className="text-[12px] text-dim">Once Red finds an attack, its replays show here.</p>
        )}
      </div>
    </Panel>
  );
}
