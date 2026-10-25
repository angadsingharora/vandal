"use client";

import { useMemo, useState } from "react";
import { cx, usd } from "@/lib/format";
import { CFO, CONTROLLER, OPERATOR, useWarRoom } from "@/lib/store";
import type { Decision, VerdictItem } from "@/lib/types";
import { IntakePanel } from "./IntakePanel";
import { Badge, Button, DecisionBadge, Empty, LiveDot, Panel, SideTag } from "./ui";

function argsLine(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v != null && v !== "" && typeof v !== "object")
    .slice(0, 4)
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
}

/** Blue's banner controls: which agent a new run gets, and how many days it works. */
export function RunOperations() {
  const s = useWarRoom();
  const [days, setDays] = useState(5);
  const operating = s.operate.phase === "running";
  return (
    <>
      <label className="sr-only" htmlFor="operator">Operator</label>
      <select
        id="operator"
        value={s.operator}
        onChange={(e) => s.setOperator(e.target.value as "reference" | "llm")}
        className="h-7 rounded border border-line bg-raised px-1.5 text-xs"
        title="The agent Guard protects: the deterministic reference Operator, or the LLM Operator that reads messy documents (O1). Takes effect on Reset demo."
      >
        <option value="reference">reference Operator</option>
        <option value="llm">LLM Operator</option>
      </select>
      <label className="sr-only" htmlFor="days">Business days</label>
      <input
        id="days"
        type="number"
        min={1}
        max={30}
        value={days}
        onChange={(e) => setDays(Math.max(1, Math.min(30, Number(e.target.value) || 1)))}
        className="num h-7 w-12 rounded border border-line bg-raised px-1.5 text-xs"
        title="Business days to operate"
      />
      <Button tone="blue" onClick={() => s.operateDays(days)} busy={operating} disabled={!s.ready} nudge={s.operate.phase === "idle"}>
        Run operations
      </Button>
      {operating && s.operate.day != null && (
        <span className="num text-[11px] text-dim">
          day {s.operate.day} · {s.operate.events} events
        </span>
      )}
    </>
  );
}

export function OperatorPanel() {
  const s = useWarRoom();
  const cases = s.entities?.cases ?? [];
  const activity = useMemo(
    () => s.activity.filter((e) => e.actor.startsWith("OP")).slice(-40).reverse(),
    [s.activity],
  );
  return (
    <Panel
      title="Operator · the finance agent"
      tag={<SideTag side="op" />}
      actions={
        <span className="flex items-center gap-2 text-[11px] text-faint">
          {s.summary?.operator === "llm" && <Badge tone="esc">LLM Operator</Badge>}
          {cases.filter((c) => c.status === "open").length} open cases
        </span>
      }
      className="min-h-[150px]"
    >
      {cases.length > 0 && (
        <ul className="border-b border-line">
          {cases.map((c) => (
            <li key={c.id} className="flex items-start gap-2 border-b border-line/50 px-3 py-1.5 last:border-b-0">
              <Badge tone={c.kind === "recovery" ? "esc" : c.kind === "escalation" ? "warn" : "dim"}>{c.kind}</Badge>
              <div className="min-w-0 flex-1">
                <div className="text-xs">
                  <span className="num">{c.subject}</span> <span className="text-dim">· {c.reason}</span>
                </div>
                {c.rationale && <div className="truncate text-[11px] text-faint">{c.rationale}</div>}
              </div>
              <Badge tone={c.status === "open" ? "warn" : "ok"}>{c.status}</Badge>
            </li>
          ))}
        </ul>
      )}
      {s.summary?.operator === "llm" && <IntakePanel />}
      {activity.length === 0 && cases.length === 0 && s.summary?.operator !== "llm" && (
        <Empty>Run operations to watch the Operator pay invoices. Each of its actions goes through Guard first.</Empty>
      )}
      <ul className="num">
        {activity.map((e) => (
          <li key={e.id} className="flex gap-2 px-3 py-0.5 text-[11px]">
            <span className="text-faint">d{e.day}</span>
            <span className="text-ink">{e.kind}</span>
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
    <li className={cx("border-b border-line/50", v.decision !== "allow" && "bg-raised/60")}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-2 px-3 py-1.5 text-left hover:bg-raised">
        <DecisionBadge decision={v.decision} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5 text-xs">
            <span className="num text-ink">{v.tool}</span>
            <span className="text-[10px] text-faint">{v.stage}</span>
            <span className="num ml-auto text-[10px] text-faint">
              d{v.day} #{v.seq}
            </span>
          </div>
          <div className="num truncate text-[11px] text-dim">
            {v.actor} · {argsLine(v.args)}
          </div>
          {v.fired.length > 0 && <div className="num truncate text-[11px] text-warn">fired {v.fired.join(", ")}</div>}
          {v.requires.length > 0 && <div className="truncate text-[11px] text-dim">requires {v.requires.join(", ")}</div>}
        </div>
      </button>
      {open && (
        <div className="num space-y-1 px-3 pb-2 pl-14 text-[10px] text-dim">
          {v.cites.length > 0 && <div>cites {v.cites.join(" ")}</div>}
          {v.cleared_by.length > 0 && <div className="text-ok">cleared by {v.cleared_by.join(" ")}</div>}
          {chain.map(([k, val]) => (
            <div key={k} className="break-all">
              {k}: {typeof val === "object" ? JSON.stringify(val) : String(val)}
            </div>
          ))}
          <div>event {v.event}</div>
        </div>
      )}
    </li>
  );
}

const FILTERS: (Decision | "all")[] = ["all", "allow", "hold", "escalate", "block"];

export function VerdictFeed({ initialFilter = "all" }: { initialFilter?: Decision | "all" } = {}) {
  const s = useWarRoom();
  const [filter, setFilter] = useState<Decision | "all">(initialFilter);
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: s.verdicts.length };
    for (const v of s.verdicts) c[v.decision] = (c[v.decision] ?? 0) + 1;
    return c;
  }, [s.verdicts]);
  const rows = useMemo(
    () => s.verdicts.filter((v) => filter === "all" || v.decision === filter).slice(-150).reverse(),
    [s.verdicts, filter],
  );
  const alerts = s.alerts.slice(-5).reverse();

  return (
    <Panel
      title="Guard verdicts · every action checked"
      tag={<SideTag side="blue" />}
      actions={s.operate.phase === "running" && <LiveDot className="text-blue" />}
      className="min-h-[240px]"
      bodyClass="flex flex-col"
    >
      <div className="flex shrink-0 gap-1 border-b border-line px-2 py-1.5">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={cx(
              "rounded-sm px-1.5 py-0.5 text-[10px] uppercase",
              filter === f ? "bg-raised text-ink" : "text-faint hover:text-ink",
            )}
          >
            {f} <span className="num">{counts[f] ?? 0}</span>
          </button>
        ))}
      </div>
      {alerts.length > 0 && (
        <ul className="shrink-0 border-b border-line">
          {alerts.map((a) => (
            <li key={a.seq} className="num break-words bg-bad/10 px-3 py-1 text-[11px] text-bad">
              ALERT d{a.day} · {String(a.invariant ?? a.kind ?? "")} {String(a.message ?? "")}
            </li>
          ))}
        </ul>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? <Empty>Every tool call the Operator makes passes Guard first. Its verdicts stream here.</Empty> : <ul>{rows.map((v) => <VerdictRow key={v.seq} v={v} />)}</ul>}
      </div>
    </Panel>
  );
}

/** Payments Guard escalated, each waiting on a human. Shared by the Operate and Approve pages. */
export function PaymentApprovals() {
  const s = useWarRoom();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const payments = s.approvals.payments;

  const decide = async (runId: string, id: string, who: typeof CONTROLLER, approve: boolean) => {
    const msg = await s.decidePayment(runId, id, who, approve);
    setNotes((n) => ({ ...n, [id]: msg }));
  };

  if (payments.length === 0) return <Empty>No payment is waiting on a human. Guard escalates over-threshold and unusual payments here.</Empty>;
  return (
    <ul>
      {payments.map((p) => (
        <li key={`${p.run_id}-${p.id}`} className="border-b border-line px-3 py-2 last:border-b-0">
          <div className="flex items-center gap-2">
            <Badge>payment</Badge>
            <span className="num text-xs">{p.invoice}</span>
            <span className="num ml-auto text-xs font-semibold">{usd(p.amount)}</span>
          </div>
          <div className="num mt-0.5 text-[11px] text-dim">
            to {p.payee_account} · asked by {p.requested_by} · {p.id}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Button tone="blue" onClick={() => decide(p.run_id, p.id, CONTROLLER, true)}>
              Approve (Controller)
            </Button>
            <Button onClick={() => decide(p.run_id, p.id, CFO, false)}>Deny (CFO)</Button>
            <Button tone="ghost" onClick={() => decide(p.run_id, p.id, OPERATOR, true)} title="Segregation of duties: Guard should refuse">
              Operator tries to approve
            </Button>
          </div>
          {notes[p.id] && <div className="mt-1 text-[11px] text-warn">{notes[p.id]}</div>}
        </li>
      ))}
    </ul>
  );
}

/** The inbox on the Operate page: escalated payments, and a pointer to a fix from Red when one
 * is waiting on the Approve page. */
export function ApprovalsInbox() {
  const s = useWarRoom();
  const patch = s.patch;
  return (
    <Panel
      title="Approvals · a human decides"
      tag={<SideTag side="blue" />}
      actions={
        <button onClick={s.loadApprovals} className="text-[11px] text-dim hover:text-ink">
          refresh
        </button>
      }
      className="min-h-[160px]"
    >
      {patch && patch.status !== "applied" && (
        <button onClick={() => void s.setStage("approve")} className="flex w-full items-center gap-2 border-b border-line bg-esc/[0.08] px-3 py-2 text-left hover:bg-esc/[0.14]">
          <Badge tone="esc">fix from Strike</Badge>
          <span className="num text-xs font-semibold">{patch.version}</span>
          <Badge tone={patch.status === "denied" ? "bad" : patch.status === "approved" ? "blue" : "warn"}>{patch.status}</Badge>
          <span className="ml-auto text-[11px] text-blue">open →</span>
        </button>
      )}
      <PaymentApprovals />
    </Panel>
  );
}

/** What Guard enforces on the live run, in one line. The before/after proof lives on Enforce. */
export function EnforcedPolicy() {
  const s = useWarRoom();
  const live = s.tabs.find((t) => t.kind === "live");
  const version = s.appliedPolicy ?? live?.policy ?? "v0";
  const info = s.policies.find((p) => p.name === version);
  return (
    <Panel title="Enforced policy" tag={<SideTag side="blue" />} className="h-auto" bodyClass="overflow-visible">
      <div className="flex flex-wrap items-baseline gap-2 p-3">
        <span className="num text-sm font-semibold text-ink">{version}</span>
        {s.appliedPolicy && <Badge tone="ok">applied from Strike</Badge>}
        <span className="text-[11px] text-dim">{info?.controls.length ? info.controls.join(" · ") : "baseline: no extra controls"}</span>
        {s.attack && (
          <button onClick={() => void s.setStage("enforce")} className="ml-auto text-[11px] text-blue hover:underline">
            before / after →
          </button>
        )}
      </div>
    </Panel>
  );
}
