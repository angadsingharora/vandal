"use client";

import { cx } from "@/lib/format";
import { Chip } from "./bits";

type Decision = "allow" | "hold" | "escalate" | "block";

const STYLE: Record<Decision, string> = {
  allow: "text-ok border-ok/40 bg-ok/10",
  hold: "text-amber border-amber/40 bg-amber/10",
  escalate: "text-esc border-esc/40 bg-esc/10",
  block: "text-red2 border-red/40 bg-red/10",
};

const ROWS: { d: Decision; tool: string; args: string; day: number; fired?: string }[] = [
  { d: "hold", tool: "vendors.change_request", args: "vendor=V-007 fields=bank channel=email", day: 0, fired: "T1.verified_account_change" },
  { d: "allow", tool: "payments.execute", args: "invoice=INV-1042 payee=BA-0007", day: 0 },
  { d: "escalate", tool: "approvals.request", args: "invoice=INV-1042 amount=$40,000.00", day: 0, fired: "v0.approval.threshold" },
  { d: "allow", tool: "invoices.validate", args: "invoice=INV-1042 match=ok", day: 0 },
  { d: "allow", tool: "ledger.reconcile", args: "transaction=BT-0024 payment=PAY-0080", day: 1 },
  { d: "allow", tool: "ledger.reconcile", args: "transaction=BT-0023 payment=PAY-0079", day: 1 },
  { d: "allow", tool: "payments.submit", args: "payment=PAY-0078", day: 0 },
  { d: "allow", tool: "payments.submit", args: "payment=PAY-0077", day: 0 },
  { d: "allow", tool: "invoices.receive", args: "vendor=V-012 number=RW-5521", day: 0 },
  { d: "allow", tool: "cash.apply", args: "deposit=DEP-0007 invoice=CI-0031", day: 0 },
  { d: "allow", tool: "payments.execute", args: "invoice=INV-1076 payee=BA-0020", day: 0 },
  { d: "allow", tool: "approvals.request", args: "invoice=INV-1061 amount=$15,953.42", day: 0 },
];

/** Blue's console (static): verdicts as they would stream, the Operator's open case, one alert. */
export function Console({ attacked }: { attacked: boolean }) {
  return (
    <aside className="glass flex h-full min-h-0 flex-col rounded-xl">
      <header className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Chip tone="blue">BLUE</Chip>
        <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-dim">Gate console</span>
        <span className="live-dot ml-1 inline-block size-1.5 rounded-full bg-blue" />
        <span className="num ml-auto text-[11px] text-faint">155 verdicts</span>
      </header>
      <div className="flex shrink-0 gap-1 border-b border-line px-2 py-1.5 text-[10px] uppercase">
        <span className="rounded-md bg-raised px-1.5 py-0.5 text-ink">all <span className="num">155</span></span>
        <span className="px-1.5 py-0.5 text-faint">allow <span className="num">152</span></span>
        <span className="px-1.5 py-0.5 text-faint">hold <span className="num">1</span></span>
        <span className="px-1.5 py-0.5 text-faint">escalate <span className="num">2</span></span>
        <span className="px-1.5 py-0.5 text-faint">block <span className="num">0</span></span>
      </div>
      {attacked && (
        <>
          <ul className="shrink-0 border-b border-line">
            <li className="num bg-red/10 px-3 py-1 text-[11px] text-red2">⚠ d0 INV-2 · PAY-0057: payee_account BA-0032 ≠ approved BA-0007</li>
            <li className="num bg-red/10 px-3 py-1 text-[11px] text-red2">⚠ d0 INV-5 · PAY-0057 executed to BA-0032, which is unverified</li>
          </ul>
          <ul className="shrink-0 border-b border-line">
            <li className="flex items-center gap-2 px-3 py-1.5 text-[11px]">
              <Chip tone="amber">recovery</Chip>
              <span className="num text-ink">PAY-0057</span>
              <span className="truncate text-dim">marked misdirected · recall asked · AP reinstated</span>
              <Chip tone="amber" className="ml-auto">open</Chip>
            </li>
          </ul>
        </>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <ul>
          {ROWS.map((v, i) => (
            <li key={i} className={cx("border-b border-line/60 px-3 py-1.5", v.d !== "allow" && "bg-raised/60")}>
              <div className="flex items-center gap-2 text-[11px]">
                <span className={cx("inline-block w-14 rounded-sm border px-1 text-center text-[9.5px] font-bold uppercase", STYLE[v.d])}>{v.d}</span>
                <span className="num truncate text-ink">{v.tool}</span>
                <span className="num ml-auto text-[10px] text-faint">d{v.day}</span>
              </div>
              <div className="num truncate pl-16 text-[10.5px] text-dim">{v.args}</div>
              {v.fired && <div className="num truncate pl-16 text-[10.5px] text-amber">fired {v.fired}</div>}
            </li>
          ))}
        </ul>
      </div>
      <footer className="border-t border-line px-3 py-2 text-[10.5px] text-faint">
        Click any verdict to see the facts Blue evaluated and the ids it cites.
      </footer>
    </aside>
  );
}
