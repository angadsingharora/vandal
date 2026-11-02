"use client";

// Shadow mode: a month of a company's real accounts payable, replayed through Guard on a clone
// of the books under the run's policy. Report only: the live run is untouched. Paste or upload
// the export as CSV (or start from the sample), and read what Guard would have allowed, held,
// escalated or blocked, and where every payment went.

import { useRef, useState } from "react";
import { cx, usd } from "@/lib/format";
import { needs } from "@/lib/rules";
import { SHADOW_COLUMNS, SHADOW_SAMPLE } from "@/lib/shadowSample";
import { useWarRoom } from "@/lib/store";
import type { Decision, ShadowReport, ShadowRow } from "@/lib/types";
import { Badge, Button, DecisionBadge, Modal, Stat } from "./ui";

const field = "num w-full rounded border border-line bg-bg px-2 text-xs";

const KIND_TEXT: Record<string, string> = {
  bill: "bill",
  payment: "payment",
  vendor_bank_change: "bank change",
  vendor_contact_change: "contact change",
  callback: "callback",
};

function RowDecision({ row }: { row: ShadowRow }) {
  if (row.decision === "unmatched") return <Badge tone="dim">unmatched</Badge>;
  return <DecisionBadge decision={row.decision as Decision} />;
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

export function ShadowDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const runId = s.focusRunId ?? s.liveRunId;
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ShadowReport | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async () => {
    if (!runId || !s.api) return;
    setError(null);
    setBusy(true);
    try {
      setReport(await s.api.shadow(runId, { csv }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File) => {
    setCsv(await file.text());
    setReport(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const sum = report?.summary;

  return (
    <Modal title="Shadow report" onClose={onClose} wide>
      <p className="text-xs leading-relaxed text-dim">
        A month of your accounts payable, replayed through Guard on a clone of {s.summary?.company ?? "the company"}&apos;s books under{" "}
        <span className="num text-ink">{s.summary?.policy ?? "v0"}</span>. Nothing here touches the live run. Each row becomes the call the agent would have made; Guard
        rules on every one. An integration posts the same CSV to <span className="num">POST /runs/{"{id}"}/shadow</span>.
      </p>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_14rem]">
        <label htmlFor="shadow-csv" className="flex flex-col gap-1 text-[11px] text-dim">
          The export, as CSV
          <textarea
            id="shadow-csv"
            value={csv}
            onChange={(e) => {
              setCsv(e.target.value);
              setReport(null);
            }}
            rows={8}
            spellCheck={false}
            placeholder={`${SHADOW_COLUMNS}\nbill,Acme Supply,A-1042,1250.00,PO-88,,,,,,,,,,,\npayment,,A-1042,,,,,,,,,,,,,`}
            className={cx(field, "py-1.5 leading-relaxed")}
          />
        </label>
        <div className="flex flex-col gap-2 text-[11px] leading-snug text-faint">
          <Button
            onClick={() => {
              setCsv(SHADOW_SAMPLE);
              setReport(null);
            }}
          >
            Load the sample month
          </Button>
          <Button onClick={() => fileRef.current?.click()}>Upload a CSV</Button>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} />
          <p>
            Kinds: <span className="num">bill</span> (vendor, number, amount, po), <span className="num">payment</span> (number), <span className="num">vendor_bank_change</span> and{" "}
            <span className="num">vendor_contact_change</span> (vendor, channel, sender, the new details), <span className="num">callback</span> (vendor, method). Vendors match by
            name, domain or id against this company&apos;s vendor master.
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-xs text-bad">
          {error}
        </p>
      )}

      {report && sum && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Rows" value={sum.rows} />
            <Stat label="Allowed" value={sum.by_decision.allow ?? 0} />
            <Stat label="Held or blocked" value={(sum.by_decision.hold ?? 0) + (sum.by_decision.block ?? 0)} tone={(sum.by_decision.hold ?? 0) + (sum.by_decision.block ?? 0) > 0 ? "ok" : undefined} />
            <Stat label="Escalated" value={sum.by_decision.escalate ?? 0} />
            <Stat label="Paid" value={usd(sum.money_through, { cents: false })} />
            <Stat label="To unverified accounts" value={usd(sum.money_unverified, { cents: false })} tone={sum.money_unverified > 0 ? "bad" : "ok"} sub={sum.money_unverified > 0 ? "money Guard let through to an account nothing verified" : "nothing reached an unverified account"} />
          </div>

          {sum.attention.length > 0 && (
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">Needs a look</h3>
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
                  <th className="px-2 py-1.5 font-medium">Guard</th>
                  <th className="px-2 py-1.5 font-medium">Why</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((r) => (
                  <tr key={r.n} className={cx("border-b border-line/60 align-top last:border-b-0", r.decision !== "allow" && "bg-raised/50")}>
                    <td className="num px-2 py-1.5 text-faint">{r.n}</td>
                    <td className="px-2 py-1.5 text-ink">
                      {KIND_TEXT[r.kind] ?? r.kind}
                      {r.input.number && <span className="num text-dim"> {r.input.number}</span>}
                      {r.input.amount != null && <span className="num text-dim"> {usd(Math.round(r.input.amount * 100))}</span>}
                      {r.ref && <span className="num text-faint"> · {r.ref}</span>}
                    </td>
                    <td className="px-2 py-1.5 text-dim">{r.vendor_name ?? r.input.vendor ?? ""}</td>
                    <td className="px-2 py-1.5">
                      <RowDecision row={r} />
                    </td>
                    <td className="px-2 py-1.5">
                      <Why row={r} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <footer className="mt-5 flex items-center gap-3 border-t border-line pt-4">
        <span className="min-w-0 flex-1 text-[11px] text-faint">Every row runs on day 0 of a fresh clone; the report is about what Guard says, not the calendar.</span>
        <Button onClick={onClose}>Close</Button>
        <Button tone="blue" onClick={run} busy={busy} disabled={!runId || !csv.trim()}>
          Run the shadow report
        </Button>
      </footer>
    </Modal>
  );
}
