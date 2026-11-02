"use client";

// Shadow mode: a month of a company's real accounts payable, replayed through Guard on a clone
// of the books under the run's policy, and under a second policy for the before/after. Report
// only: the live run is untouched. Paste or upload the export as it comes out of the accounting
// system (the columns are read through aliases, and the mapping shows before anything runs), or
// start from the sample. The report is kept on the server and has its own page to send on.

import { useEffect, useRef, useState } from "react";
import { cx } from "@/lib/format";
import { SHADOW_COLUMNS, SHADOW_SAMPLE } from "@/lib/shadowSample";
import { useWarRoom } from "@/lib/store";
import type { ShadowMapping, ShadowReport } from "@/lib/types";
import { headline, KIND_TEXT, ShadowReportBody } from "./ShadowReportBody";
import { Button, Modal } from "./ui";

const field = "num w-full rounded border border-line bg-bg px-2 text-xs";

function Mapping({ m }: { m: ShadowMapping }) {
  return (
    <div className="rounded border border-line bg-panel px-3 py-2 text-[11px] leading-relaxed">
      {m.problem ? (
        <p className="text-bad">{m.problem}</p>
      ) : (
        <p className="text-dim">
          <span className="text-ink">
            {m.rows} {m.rows === 1 ? "row" : "rows"}
          </span>
          {Object.keys(m.kinds).length > 0 && (
            <>
              :{" "}
              {Object.entries(m.kinds)
                .map(([k, n]) => `${n} ${KIND_TEXT[k] ?? k}${n === 1 ? "" : "s"}`)
                .join(", ")}
            </>
          )}
          .
        </p>
      )}
      <p className="mt-1 text-dim">
        Read as{" "}
        {m.columns.map((c, i) => (
          <span key={c.source}>
            {i > 0 && ", "}
            <span className="num text-ink">{c.source}</span>
            {c.source.trim().toLowerCase() !== c.read_as && (
              <>
                {" "}
                → <span className="num">{c.read_as}</span>
              </>
            )}
          </span>
        ))}
        {m.ignored.length > 0 && (
          <>
            . Ignored: <span className="num text-faint">{m.ignored.join(", ")}</span>
          </>
        )}
        .
      </p>
    </div>
  );
}

export function ShadowDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const runId = s.focusRunId ?? s.liveRunId;
  const current = s.summary?.policy ?? "v0";
  const others = s.policies.map((p) => p.name).filter((n) => n !== current);
  const [csv, setCsv] = useState("");
  const [compare, setCompare] = useState<string>(others.includes("v1") ? "v1" : (others[0] ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapping, setMapping] = useState<ShadowMapping | null>(null);
  const [report, setReport] = useState<ShadowReport | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // The mapping, a moment after the text settles: which column feeds which, before anything runs.
  useEffect(() => {
    const api = s.api;
    if (!api || !csv.trim()) {
      setMapping(null);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      api
        .shadowMapping(csv)
        .then((m) => alive && setMapping(m))
        .catch(() => alive && setMapping(null));
    }, 350);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [csv, s.api]);

  const run = async () => {
    if (!runId || !s.api) return;
    setError(null);
    setBusy(true);
    try {
      setReport(await s.api.shadow(runId, { csv, compare: compare || null }));
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

  return (
    <Modal title="Shadow report" onClose={onClose} wide>
      <p className="text-xs leading-relaxed text-dim">
        A month of your accounts payable, replayed through Guard on a clone of {s.summary?.company ?? "the company"}&apos;s books under{" "}
        <span className="num text-ink">{current}</span>
        {compare && (
          <>
            , and again under <span className="num text-ink">{compare}</span> for the before and after
          </>
        )}
        . Nothing here touches the live run. Each row becomes the call the agent would have made; Guard rules on every one. An integration posts the same
        CSV to <span className="num">POST /runs/{"{id}"}/shadow</span>.
      </p>

      <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_14rem]">
        <label htmlFor="shadow-csv" className="flex flex-col gap-1 text-[11px] text-dim">
          The export, as CSV, as it comes out of QuickBooks, Bill.com, NetSuite or a spreadsheet
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
          <label htmlFor="shadow-compare" className="mt-1 flex flex-col gap-1 text-[11px] text-dim">
            Compare against
            <select id="shadow-compare" value={compare} onChange={(e) => setCompare(e.target.value)} className={cx(field, "h-8")}>
              <option value="">nothing, {current} alone</option>
              {others.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <p>
            Column names from the usual systems are read as is (Vendor Name, Invoice #, Transaction Type, PO Number…). Kinds: bill, payment, bank change,
            contact change, callback. Vendors match by name, domain or id against this company&apos;s vendor master.
          </p>
        </div>
      </div>

      {mapping && !report && (
        <div className="mt-3">
          <Mapping m={mapping} />
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-xs text-bad">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-5">
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-sm font-semibold text-ink">{headline(report)}</h2>
            {report.job_id && (
              <a
                href={`/report/shadow/${report.job_id}`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-ink underline"
                title="The same report on its own page, to print or send on. It lives on the server as long as it runs."
              >
                Open the report
              </a>
            )}
          </div>
          <ShadowReportBody report={report} />
        </div>
      )}

      <footer className="mt-5 flex items-center gap-3 border-t border-line pt-4">
        <span className="min-w-0 flex-1 text-[11px] text-faint">Every row runs on day 0 of a fresh clone; the report is about what Guard says, not the calendar.</span>
        <Button onClick={onClose}>Close</Button>
        <Button tone="blue" onClick={run} busy={busy} disabled={!runId || !csv.trim() || (mapping?.problem != null)}>
          Run the shadow report
        </Button>
      </footer>
    </Modal>
  );
}
