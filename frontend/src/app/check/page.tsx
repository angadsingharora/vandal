"use client";

// The front door for someone who has no agent to connect yet: a month of accounts payable goes
// in, and what Guard would have done to every row comes out, under today's rules and under the
// rule Vandal proposes. One click runs the sample month; an upload runs your own, with vendors
// the demo company doesn't know taken from the file (`enroll`). The same report the workspace's
// shadow dialog builds, on a page of its own.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getApi, type VandalApi } from "@/lib/api";
import { usd } from "@/lib/format";
import { SHADOW_SAMPLE } from "@/lib/shadowSample";
import type { ShadowMapping, ShadowReport } from "@/lib/types";
import { KIND_TEXT, ShadowReportBody } from "@/components/ShadowReportBody";
import { linkClass, SiteFooter, SiteHeader } from "@/components/site/SiteShell";
import { Button } from "@/components/ui";

const BEFORE = "v0";
const AFTER = "v1";

/** The API, once it answers. A sleeping host takes about a minute; keep asking until it wakes. */
async function connect(onSlow: () => void): Promise<VandalApi> {
  const api = await getApi();
  for (let tries = 0; ; tries++) {
    try {
      await api.settings();
      return api;
    } catch (err) {
      if (tries >= 40) throw err;
      if (tries === 1) onSlow();
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

/** A run of the demo company under the baseline rules to clone from: this browser's, or a new one. */
async function baseline(api: VandalApi): Promise<string> {
  const mine = await api.listRuns().catch(() => []);
  const run = mine.filter((r) => r.kind === "operate" && r.policy === BEFORE).at(-1);
  return run ? run.run_id : (await api.createRun({ policy: BEFORE })).run_id;
}

/** The finding in a sentence, for someone who has never heard of a policy version. */
function finding(report: ShadowReport): string {
  const through = report.summary.money_unverified;
  const after = report.compare?.summary.money_unverified ?? through;
  if (through === 0) return "Every payment went to a verified account.";
  const money = usd(through, { cents: false });
  if (after === 0) return `${money} went to accounts nobody verified. One rule would have stopped all of it.`;
  if (after < through) return `${money} went to accounts nobody verified. One rule would have stopped ${usd(through - after, { cents: false })} of it.`;
  return `${money} went to accounts nobody verified.`;
}

export default function CheckPage() {
  const [api, setApi] = useState<VandalApi | null>(null);
  const [slow, setSlow] = useState(false);
  const [down, setDown] = useState<string | null>(null);
  const [busy, setBusy] = useState<"sample" | "own" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [own, setOwn] = useState<{ name: string; csv: string } | null>(null);
  const [mapping, setMapping] = useState<ShadowMapping | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    connect(() => alive && setSlow(true)).then(
      (a) => alive && setApi(a),
      (err) => alive && setDown(err instanceof Error ? err.message : String(err)),
    );
    return () => {
      alive = false;
    };
  }, []);

  const run = async (which: "sample" | "own", csv: string) => {
    if (!api) return;
    setBusy(which);
    setError(null);
    setReport(null);
    try {
      const runId = await baseline(api);
      // The sample's vendors are the demo company's; a file of your own brings its own.
      // `enroll` goes only with an upload, so the sample still runs against an API from before it.
      setReport(await api.shadow(runId, { csv, compare: AFTER, ...(which === "own" ? { enroll: true } : {}) }));
      setTimeout(() => reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const pick = async (file: File) => {
    const csv = await file.text();
    if (fileRef.current) fileRef.current.value = "";
    setOwn({ name: file.name, csv });
    setMapping(null);
    setReport(null);
    setError(null);
    try {
      setMapping((await api?.shadowMapping(csv)) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const changes = mapping ? (mapping.kinds.vendor_bank_change ?? 0) + (mapping.kinds.vendor_contact_change ?? 0) : 0;
  const status = down ? "The server is not answering. Try again in a minute." : !api ? (slow ? "Waking the server. It sleeps when idle and takes about a minute." : "Connecting…") : null;

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 sm:px-10 lg:py-12">
        <SiteHeader current="/check" />
        <main className="mt-16 lg:mt-20">
          <h1 className="max-w-3xl text-4xl font-bold leading-[1.05] tracking-tight text-ink sm:text-5xl">Which of last month&apos;s payments went to an account nobody verified?</h1>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-dim">
            Vandal replays a month of accounts payable through its checks, row by row, and tells you what it would have allowed, held, or sent to a person, and
            where the money ended up. Nothing is connected and no money moves.
          </p>

          <div className="mt-10 grid gap-px overflow-hidden rounded-md border border-line bg-line lg:grid-cols-2">
            <section className="bg-panel p-6">
              <h2 className="text-sm font-semibold text-ink">Start with the sample month</h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
                Fifteen rows from a property manager&apos;s books. One of them is an emailed bank change from a lookalike domain, and a $40,000 payment follows
                it.
              </p>
              <Button tone="blue" onClick={() => void run("sample", SHADOW_SAMPLE)} busy={busy === "sample"} disabled={!api || busy !== null} className="mt-5 h-11 px-6 text-sm font-semibold">
                Run the sample month
              </Button>
            </section>

            <section className="bg-panel p-6">
              <h2 className="text-sm font-semibold text-ink">Or run your own</h2>
              <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
                A CSV export of bills and payments from QuickBooks, Bill.com, NetSuite, Xero or a spreadsheet. Your vendors are read from the file. Findings come
                from the rows where a vendor&apos;s bank details or contact changed, so add those if your export leaves them out (
                <a href={`data:text/csv;charset=utf-8,${encodeURIComponent(SHADOW_SAMPLE)}`} download="vandal-sample-month.csv" className={linkClass}>
                  the sample shows the shape
                </a>
                ).
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button onClick={() => fileRef.current?.click()} disabled={!api || busy !== null} className="h-11 px-6 text-sm font-semibold">
                  {own ? "Choose another file" : "Choose a CSV"}
                </Button>
                {own && mapping && !mapping.problem && (
                  <Button tone="blue" onClick={() => void run("own", own.csv)} busy={busy === "own"} disabled={busy !== null} className="h-11 px-6 text-sm font-semibold">
                    Run {mapping.rows} {mapping.rows === 1 ? "row" : "rows"}
                  </Button>
                )}
                <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && void pick(e.target.files[0])} />
              </div>
              {own && mapping && (
                <div className="mt-4 text-xs leading-relaxed text-dim">
                  {mapping.problem ? (
                    <p className="text-bad">
                      {own.name}: {mapping.problem}
                    </p>
                  ) : (
                    <>
                      <p>
                        <span className="text-ink">{own.name}</span>:{" "}
                        {Object.entries(mapping.kinds)
                          .map(([k, n]) => `${n} ${KIND_TEXT[k] ?? k}${n === 1 ? "" : "s"}`)
                          .join(", ")}
                        . Read {mapping.columns.map((c) => c.source).join(", ")}
                        {mapping.ignored.length > 0 && <>; ignored {mapping.ignored.join(", ")}</>}.
                      </p>
                      {changes === 0 && (
                        <p className="mt-1.5 text-warn">
                          This file has no bank or contact changes, so every payment will go to the account on file and the report will have little to say.
                        </p>
                      )}
                    </>
                  )}
                </div>
              )}
              <p className="mt-4 text-xs leading-relaxed text-faint">
                This is a demo server with no accounts. Mask real account and routing numbers before you upload; the checks only need to tell one account from
                another.
              </p>
            </section>
          </div>

          {status && (
            <p role="status" className="mt-4 text-xs text-dim">
              {status}
            </p>
          )}
          {error && (
            <p role="alert" className="mt-4 text-xs text-bad">
              {error}
            </p>
          )}

          {report && (
            <div ref={reportRef} className="mt-14 scroll-mt-8 border-t border-line pt-10">
              <h2 className="max-w-4xl text-2xl font-bold leading-tight tracking-tight text-ink sm:text-3xl">{finding(report)}</h2>
              <p className="mt-3 max-w-3xl text-[13px] leading-relaxed text-dim">
                {report.summary.rows} rows, once under the baseline rules (<span className="num text-ink">{report.policy}</span>) and once with the rule Vandal
                proposes (<span className="num text-ink">{report.compare?.policy ?? AFTER}</span>): a changed bank account pays out only after a call back to the
                contact already on file.
                {report.enrolled && report.enrolled.length > 0 && (
                  <>
                    {" "}
                    {report.enrolled.length} {report.enrolled.length === 1 ? "vendor was" : "vendors were"} read from your file and treated as on file, with a
                    verified account, before the month began.
                  </>
                )}
              </p>
              <div className="mt-8">
                <ShadowReportBody report={report} />
              </div>

              <div className="mt-12 grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-3">
                {report.job_id && (
                  <div className="bg-panel p-5">
                    <h3 className="text-sm font-semibold text-ink">Send it on</h3>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-dim">The same report on a page of its own, to print or save as a PDF.</p>
                    <a href={`/report/shadow/${report.job_id}`} target="_blank" rel="noreferrer" className={`${linkClass} mt-3 inline-block text-[13px]`}>
                      Open the report
                    </a>
                  </div>
                )}
                <div className="bg-panel p-5">
                  <h3 className="text-sm font-semibold text-ink">Put an agent behind it</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-dim">Connect an AI agent to the demo company and watch the same checks rule on every call it makes.</p>
                  <Link href="/?workspace=1" className={`${linkClass} mt-3 inline-block text-[13px]`}>
                    Open the workspace
                  </Link>
                </div>
                <div className="bg-panel p-5">
                  <h3 className="text-sm font-semibold text-ink">Run it on your real books</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-dim">Tell us what your payables setup looks like and we will run a full month with you.</p>
                  <Link href="/contact" className={`${linkClass} mt-3 inline-block text-[13px]`}>
                    Talk to us
                  </Link>
                </div>
              </div>
            </div>
          )}
        </main>
        <SiteFooter className="mt-20" />
      </div>
    </div>
  );
}
