"use client";

// The body of a shadow report, shared by the dialog in the workspace and the standalone page at
// /report/shadow/{job}: the numbers (before and after, when the month ran under two policies),
// what the compared policy changed, what needs a look, and every row with Guard's reason.

import { cx, usd } from "@/lib/format";
import { needs } from "@/lib/rules";
import type { Decision, ShadowReport, ShadowRow, ShadowSummary } from "@/lib/types";
import { Badge, DecisionBadge, Stat } from "./ui";

export const KIND_TEXT: Record<string, string> = {
  bill: "bill",
  payment: "payment",
  vendor_bank_change: "bank change",
  vendor_contact_change: "contact change",
  callback: "callback",
};

function RowDecision({ decision }: { decision: ShadowRow["decision"] }) {
  if (decision === "unmatched") return <Badge tone="dim">unmatched</Badge>;
  return <DecisionBadge decision={decision as Decision} />;
}

function Why({ row }: { row: ShadowRow }) {
  const worst = row.steps.find((s) => s.decision === row.decision);
  if (row.note) return <span className="text-dim">{row.note}</span>;
  if (row.kind === "payment" && row.paid) {
    const bad = row.payee_status !== "verified";
    return (
      <span className={bad ? "text-bad" : "text-dim"}>
        {usd(row.amount_cents ?? 0)} to <span className="num">{row.payee_account}</span>, {row.payee_status}
        {bad && row.payee_source ? ` (${row.payee_source})` : ""}
      </span>
    );
  }
  if (!worst || worst.decision === "allow") return <span className="text-faint">nothing fired</span>;
  return (
    <span className="text-dim">
      <span className="num text-warn">{worst.fired.join(", ")}</span>
      {worst.requires.map((r) => (
        <span key={r.check}> · {needs(r)}</span>
      ))}
    </span>
  );
}

const stopped = (s: ShadowSummary) => (s.by_decision.hold ?? 0) + (s.by_decision.block ?? 0);

function Compare({ before, after }: { before: ShadowSummary; after: ShadowSummary }) {
  const rows: { label: string; b: number; a: number; fmt: (n: number) => string; better: "down" | "up" | "none" }[] = [
    { label: "Allowed", b: before.by_decision.allow ?? 0, a: after.by_decision.allow ?? 0, fmt: String, better: "none" },
    { label: "Held or blocked", b: stopped(before), a: stopped(after), fmt: String, better: "up" },
    { label: "Escalated to a person", b: before.by_decision.escalate ?? 0, a: after.by_decision.escalate ?? 0, fmt: String, better: "none" },
    { label: "Paid", b: before.money_through, a: after.money_through, fmt: (n) => usd(n, { cents: false }), better: "none" },
    { label: "Stopped before payment", b: before.money_stopped, a: after.money_stopped, fmt: (n) => usd(n, { cents: false }), better: "up" },
    { label: "To unverified accounts", b: before.money_unverified, a: after.money_unverified, fmt: (n) => usd(n, { cents: false }), better: "down" },
  ];
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
          <th className="py-2 pr-4 font-semibold"></th>
          <th className="num py-2 pr-4 text-right font-semibold">{before.policy}</th>
          <th className="num py-2 text-right font-semibold">{after.policy}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const improved = r.better === "down" ? r.a < r.b : r.better === "up" ? r.a > r.b : false;
          const bad = r.label === "To unverified accounts";
          return (
            <tr key={r.label} className="border-b border-line last:border-b-0">
              <td className="py-2 pr-4 text-dim">{r.label}</td>
              <td className={cx("num py-2 pr-4 text-right", bad && r.b > 0 ? "text-bad" : "text-ink")}>{r.fmt(r.b)}</td>
              <td className={cx("num py-2 text-right", improved ? "text-ok" : bad && r.a > 0 ? "text-bad" : "text-ink")}>{r.fmt(r.a)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Tiles({ sum }: { sum: ShadowSummary }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
      <Stat label="Rows" value={sum.rows} />
      <Stat label="Allowed" value={sum.by_decision.allow ?? 0} />
      <Stat label="Held or blocked" value={stopped(sum)} tone={stopped(sum) > 0 ? "ok" : undefined} />
      <Stat label="Escalated" value={sum.by_decision.escalate ?? 0} />
      <Stat label="Paid" value={usd(sum.money_through, { cents: false })} />
      <Stat
        label="To unverified accounts"
        value={usd(sum.money_unverified, { cents: false })}
        tone={sum.money_unverified > 0 ? "bad" : "ok"}
        sub={sum.money_unverified > 0 ? "money Guard let through to an account nothing verified" : "nothing reached an unverified account"}
      />
    </div>
  );
}

export function headline(report: ShadowReport): string {
  const d = report.delta;
  const sum = report.summary;
  if (d && report.compare) {
    const saved = -d.money_unverified;
    if (saved > 0) return `${d.after} would have kept ${usd(saved, { cents: false })} away from unverified accounts.`;
    if (sum.money_unverified === 0) return `Nothing reached an unverified account under ${d.before}, and ${d.after} changes ${d.moved.length} ${d.moved.length === 1 ? "row" : "rows"}.`;
    return `${d.after} changes ${d.moved.length} of ${sum.rows} rows.`;
  }
  if (sum.money_unverified > 0) return `${usd(sum.money_unverified, { cents: false })} reached accounts nothing verified under ${sum.policy}.`;
  return `Nothing reached an unverified account under ${sum.policy}.`;
}

function Heading({ children }: { children: React.ReactNode }) {
  return <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">{children}</h3>;
}

export function ShadowReportBody({ report }: { report: ShadowReport }) {
  const sum = report.summary;
  const other = report.compare;
  const d = report.delta;
  const byN = new Map((other?.rows ?? []).map((r) => [r.n, r]));
  return (
    <div className="space-y-5">
      {other && d ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            <Heading>
              {sum.policy} against {other.policy}
            </Heading>
            <div className="mt-2">
              <Compare before={sum} after={other.summary} />
            </div>
          </div>
          <div>
            <Heading>What {d.after} changes</Heading>
            {d.moved.length === 0 ? (
              <p className="mt-2 text-xs text-faint">No row decides differently.</p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {d.moved.map((m) => (
                  <li key={m.n} className="rounded border border-line px-3 py-2 text-xs">
                    <span className="num text-faint">#{m.n}</span> <span className="text-ink">{KIND_TEXT[m.kind] ?? m.kind}</span>
                    {m.vendor_name && <span className="text-dim"> · {m.vendor_name}</span>}
                    {m.amount_cents != null && <span className="num text-dim"> · {usd(m.amount_cents)}</span>}
                    <span className="ml-2 inline-flex items-center gap-1 align-middle">
                      <RowDecision decision={m.before as ShadowRow["decision"]} />
                      <span className="text-faint">→</span>
                      <RowDecision decision={m.after as ShadowRow["decision"]} />
                    </span>
                    {m.summary && <div className="mt-0.5 text-dim">{m.summary}</div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : (
        <Tiles sum={sum} />
      )}

      {sum.attention.length > 0 && (
        <div>
          <Heading>Needs a look under {sum.policy}</Heading>
          <ul className="mt-2 space-y-1.5">
            {sum.attention.map((a, i) => (
              <li key={i} className={cx("rounded border px-3 py-2 text-xs", a.decision === "paid_unverified" ? "border-bad/40 bg-bad/[0.06]" : "border-warn/40 bg-warn/[0.05]")}>
                <span className="num text-faint">#{a.n}</span> <span className="text-ink">{KIND_TEXT[a.kind] ?? a.kind}</span>
                {a.vendor_name && <span className="text-dim"> · {a.vendor_name}</span>}
                <div className="mt-0.5 text-dim">{a.summary}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto rounded border border-line">
        <table className="w-full border-collapse bg-panel text-xs">
          <thead>
            <tr className="border-b border-line text-left text-[10px] uppercase tracking-wider text-faint">
              <th className="px-2 py-1.5 font-medium">#</th>
              <th className="px-2 py-1.5 font-medium">Row</th>
              <th className="px-2 py-1.5 font-medium">Vendor</th>
              <th className="px-2 py-1.5 font-medium">{other ? sum.policy : "Guard"}</th>
              {other && <th className="px-2 py-1.5 font-medium">{other.policy}</th>}
              <th className="px-2 py-1.5 font-medium">Why{other ? ` under ${other.policy}` : ""}</th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((r) => {
              const twin = byN.get(r.n);
              const shown = twin ?? r;
              const moved = twin != null && twin.decision !== r.decision;
              return (
                <tr key={r.n} className={cx("border-b border-line/60 align-top last:border-b-0", (moved || shown.decision !== "allow") && "bg-raised/50")}>
                  <td className="num px-2 py-1.5 text-faint">{r.n}</td>
                  <td className="px-2 py-1.5 text-ink">
                    {KIND_TEXT[r.kind] ?? r.kind}
                    {r.input.number && <span className="num text-dim"> {r.input.number}</span>}
                    {r.input.amount != null && <span className="num text-dim"> {usd(Math.round(r.input.amount * 100))}</span>}
                    {r.ref && <span className="num text-faint"> · {r.ref}</span>}
                  </td>
                  <td className="px-2 py-1.5 text-dim">{r.vendor_name ?? r.input.vendor ?? ""}</td>
                  <td className="px-2 py-1.5">
                    <RowDecision decision={r.decision} />
                  </td>
                  {twin && (
                    <td className="px-2 py-1.5">
                      <RowDecision decision={twin.decision} />
                    </td>
                  )}
                  <td className="px-2 py-1.5">
                    <Why row={shown} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
