"use client";

// Pieces shared by the Fix, Prove, Approve and Enforce pages: how a control is shown in full,
// how a CEGIS iteration reads, and the before/after scorecard.

import { cx, moveLine, pct, usd } from "@/lib/format";
import { readRule } from "@/lib/rules";
import type { Control, LogEntry, Policy, Scorecard } from "@/lib/types";
import { Badge, Table, td } from "./ui";

/** What each verification check proves (DESIGN 10). */
export const CHECK_HELP: Record<string, string> = {
  replay: "The minimal counterexample, replayed under the new policy, is held or blocked",
  "re-search": "The whole bounded search space under the new policy finds no violation within k",
  variants: "Held-out Red content (other vendors, amounts, channels, deepfake confirmations) the synthesizer never saw",
  regression: "About 25 legitimate cases, including a real bank change verified by callback, all still complete",
  "legit ops": "All 80 seeded invoices replayed: holds and blocks on legitimate payments",
  invariants: "Every invariant holds in every legitimate run",
};

export const OUTCOME_TONE: Record<string, "ok" | "bad" | "warn" | "dim"> = {
  survived: "ok",
  counterexample: "bad",
  false_positive: "warn",
  lint: "dim",
};

/** Short outcome names for narrow tables. */
export const OUTCOME_SHORT: Record<string, string> = {
  survived: "survived",
  counterexample: "attacked",
  false_positive: "blocks legit",
  lint: "lint",
};

/** "T2 ApprovalBinding(...)" → "T2". */
export function code(control: string): string {
  return control.split(" ")[0];
}

/** "T2 ApprovalBinding(a=1, b=2)" → "ApprovalBinding". */
export function name(control: string): string {
  return control.replace(/\(.*\)$/, "").split(" ").slice(1).join(" ") || control;
}

export function params(control: string): string {
  return control.match(/\((.*)\)$/)?.[1] ?? "";
}

function show(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** One control, spelled out: its code and name, what it is for, what Guard does under it in
 * plain English (one sentence per compiled check), and the exact parameters behind that. */
export function ControlCard({ control, label }: { control: Control; label?: string }) {
  const entries = Object.entries(control.params ?? {});
  const r = readRule(control);
  return (
    <div className="rounded border border-line bg-raised/40 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        {label && <span className="num text-xs font-bold text-ok">{label}</span>}
        <span className="text-[13px] font-semibold text-ink">{r.name}</span>
        <span className="num text-[10px] text-faint">{control.template}</span>
      </div>
      {r.gist && <p className="mt-0.5 text-[11px] italic leading-snug text-dim">{r.gist}</p>}
      <ul className="mt-1.5 space-y-1">
        {r.does.map((line, i) => (
          <li key={i} className="flex gap-2 text-xs leading-snug text-ink/90">
            <span aria-hidden className="mt-[5px] size-1.5 shrink-0 rounded-full bg-ok/70" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
      {entries.length > 0 && (
        <details className="mt-1.5 text-[11px]">
          <summary className="cursor-pointer text-faint hover:text-dim">Parameters</summary>
          <dl className="num mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
            {entries.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-faint">{k}</dt>
                <dd className="break-all text-ink/90">{show(v)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

/** Every control in a policy, in full. `chosen` gives the codes ("T2 ...") in the same order. */
export function ControlList({ policy, chosen }: { policy: Policy; chosen?: string[] }) {
  if (policy.controls.length === 0) return <p className="text-xs text-dim">No controls: the baseline.</p>;
  return (
    <div className="space-y-1.5">
      {policy.controls.map((c, i) => (
        <ControlCard key={i} control={c} label={chosen?.[i] ? code(chosen[i]) : undefined} />
      ))}
    </div>
  );
}

/** A control named only by its string, when the policy object isn't at hand. */
export function ControlLine({ control }: { control: string }) {
  return (
    <div className="rounded border border-line bg-raised/40 px-3 py-1.5">
      <span className="num text-xs font-bold text-ok">{code(control)}</span>{" "}
      <span className="text-xs font-semibold text-ink">{name(control)}</span>
      {params(control) && <div className="num mt-0.5 break-all text-[11px] text-dim">{params(control)}</div>}
    </div>
  );
}

export function PolicyDiff({ policy }: { policy: Policy }) {
  return (
    <pre className="num overflow-x-auto rounded border border-line bg-bg p-2 text-[11px] leading-relaxed">
      {policy.diff.map((line, i) => (
        <div key={i} className={line.startsWith("+") ? "text-ok" : line.startsWith("-") ? "text-bad" : "text-dim"}>
          {line}
        </div>
      ))}
    </pre>
  );
}

/** One CEGIS iteration. A survivor shows its full rule set, since that is what gets installed. */
export function LogItem({ e }: { e: LogEntry }) {
  const survived = e.outcome === "survived";
  const rules = [...e.base, e.candidate];
  return (
    <li className={cx("border-b border-line/50 px-3 py-1.5", survived && "bg-ok/[0.06]")}>
      <div className="flex items-center gap-2 text-xs">
        <span className="num text-faint">it{e.iteration}</span>
        <span className="num font-medium text-ink">{rules.map(code).join(" + ")}</span>
        <Badge tone={OUTCOME_TONE[e.outcome] ?? "dim"}>{OUTCOME_SHORT[e.outcome] ?? e.outcome.replace("_", " ")}</Badge>
        <span className="ml-auto text-[10px] text-faint">{e.source}</span>
      </div>
      {survived ? (
        <ul className="num mt-1 space-y-0.5 text-[11px]">
          {rules.map((r) => (
            <li key={r} className="break-all">
              <span className="text-ok">{code(r)}</span> <span className="text-ink">{name(r)}</span>
              {params(r) && <span className="text-dim">({params(r)})</span>}
            </li>
          ))}
        </ul>
      ) : (
        <div className="num truncate text-[11px] text-dim" title={e.candidate}>
          {name(e.candidate)} {params(e.candidate) && `(${params(e.candidate)})`}
        </div>
      )}
      <div className="text-[11px] text-dim">{e.detail}</div>
      {e.counterexample && <div className="num mt-0.5 break-all text-[11px] text-bad">↳ {e.counterexample.map(moveLine).join(" → ")}</div>}
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
