"use client";

// A shadow report on its own page: the month a finance team exported, replayed through Guard,
// written to be read, printed, or sent to the person who decides. The same report the workspace
// dialog shows, fetched by its job id.

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getApi, type VandalApi } from "@/lib/api";
import { SITE } from "@/lib/site";
import type { Job, ShadowReport } from "@/lib/types";
import { headline, ShadowReportBody } from "@/components/ShadowReportBody";

export default function ShadowReportPage({ params }: { params: Promise<{ job: string }> }) {
  const { job: jobId } = use(params);
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getApi()
      .then((api: VandalApi) => api.job<ShadowReport>(jobId))
      .then((j: Job<ShadowReport>) => {
        if (!alive) return;
        if (j.kind !== "shadow") throw new Error(`${jobId} is a ${j.kind} job, not a shadow report`);
        if (j.status !== "done" || !j.result) throw new Error(`${jobId} is ${j.status}`);
        setReport({ ...j.result, job_id: jobId });
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [jobId]);

  const sum = report?.summary;
  const other = report?.compare;

  return (
    <div className="min-h-screen bg-bg print:bg-white">
      <div className="mx-auto w-full max-w-5xl px-6 py-10 sm:px-10">
        <header className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <Link href="/" className="text-base font-semibold tracking-tight text-ink">
              {SITE.name}
            </Link>
            <span className="ml-3 text-xs uppercase tracking-wider text-faint">Shadow report</span>
          </div>
          <div className="flex items-baseline gap-4 text-xs print:hidden">
            <button onClick={() => window.print()} className="text-ink underline underline-offset-4 decoration-line hover:decoration-ink">
              Print or save as PDF
            </button>
            <Link href="/?workspace=1" className="text-dim underline-offset-4 hover:text-ink hover:underline">
              Back to the workspace
            </Link>
          </div>
        </header>

        {error && (
          <div className="mt-12">
            <h1 className="text-2xl font-bold tracking-tight text-ink">No report here.</h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-dim">
              {error}. Shadow reports live on the server as long as it runs; run the month again from the workspace and open the report from there.
            </p>
          </div>
        )}

        {!report && !error && <p className="mt-12 text-sm text-dim">Loading the report…</p>}

        {report && sum && (
          <main className="mt-12">
            <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink sm:text-4xl">{headline(report)}</h1>
            <p className="mt-4 max-w-3xl text-[15px] leading-relaxed text-dim">
              {sum.rows} rows of accounts payable at <span className="text-ink">{report.company}</span>, replayed through Guard on a clone of the books under{" "}
              <span className="num text-ink">{sum.policy}</span>
              {other && (
                <>
                  {" "}
                  and again under <span className="num text-ink">{other.policy}</span>
                </>
              )}
              . Each row became the calls the agent would have made, and Guard ruled on every one. Nothing here moved real money; the live books were not
              touched.
            </p>
            <div className="mt-10">
              <ShadowReportBody report={report} />
            </div>
            <footer className="mt-12 border-t border-line pt-6 text-xs text-faint">
              {SITE.name} · {SITE.tagline}. Every row ran on day 0 of a fresh clone; the report is about what Guard says, not the calendar. Report{" "}
              <span className="num">{jobId}</span>.
            </footer>
          </main>
        )}
      </div>
    </div>
  );
}
