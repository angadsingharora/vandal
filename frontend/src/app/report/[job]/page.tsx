"use client";

// The evidence report: one verification, written for a person. The same pack the Prove page
// shows and the JSON download carries, laid out to be read, printed, or handed to an auditor:
// the verdict, the rule in plain English, every check and what it measured, the scorecard before
// and after, and the attack that started it.

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { getApi, type VandalApi } from "@/lib/api";
import { cx, moveLine, pct, usd } from "@/lib/format";
import { readRule } from "@/lib/rules";
import { SITE } from "@/lib/site";
import type { EvidencePack, Job, Policy } from "@/lib/types";

const CHECK_HELP: Record<string, string> = {
  replay: "The minimal counterexample, replayed under the new policy, is held or blocked.",
  "re-search": "The whole bounded search space under the new policy finds no violation within k.",
  variants: "Held-out attack content the synthesizer never saw: other vendors, amounts, channels, deepfake confirmations.",
  regression: "Legitimate cases, including a real bank change verified by callback, all still complete.",
  "legit ops": "Every seeded invoice replayed: holds and blocks on legitimate payments.",
  invariants: "Every invariant holds in every legitimate run.",
};

function Row({ label, before, after, fmt }: { label: string; before?: number; after?: number; fmt: (n: number) => string }) {
  const improved = before != null && after != null && after < before;
  return (
    <tr className="border-b border-line last:border-b-0">
      <td className="py-2 pr-4 text-dim">{label}</td>
      <td className="num py-2 pr-4 text-right text-ink">{before == null ? "—" : fmt(before)}</td>
      <td className={cx("num py-2 text-right", improved ? "text-ok" : "text-ink")}>{after == null ? "—" : fmt(after)}</td>
    </tr>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10 break-inside-avoid border-t border-line pt-6">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-faint">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default function ReportPage({ params }: { params: Promise<{ job: string }> }) {
  const { job: jobId } = use(params);
  const [job, setJob] = useState<Job<EvidencePack> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getApi()
      .then((api: VandalApi) => api.job<EvidencePack>(jobId))
      .then((j) => {
        if (!alive) return;
        if (j.kind !== "verify") throw new Error(`${jobId} is a ${j.kind} job, not a verification`);
        if (j.status !== "done" || !j.result) throw new Error(`${jobId} is ${j.status}`);
        setJob(j);
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [jobId]);

  const pack = job?.result ?? null;
  const policy = (job?.meta.policy_json as Policy | undefined) ?? null;
  const before = pack?.metrics.before;
  const after = pack?.metrics.after;
  const passed = pack?.checks.filter((c) => c.passed).length ?? 0;

  return (
    <div className="min-h-screen bg-bg print:bg-white">
      <div className="mx-auto w-full max-w-3xl px-6 py-10 sm:px-10">
        <header className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <Link href="/" className="text-base font-semibold tracking-tight text-ink">
              {SITE.name}
            </Link>
            <span className="ml-3 text-xs uppercase tracking-wider text-faint">Evidence report</span>
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
              {error}. Verifications live on the server as long as it runs; verify the control again and open the report from the Prove page.
            </p>
          </div>
        )}

        {!pack && !error && <p className="mt-12 text-sm text-dim">Loading the verification…</p>}

        {pack && (
          <main className="mt-12">
            <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink sm:text-4xl">
              {pack.version} is {pack.approvable ? "approvable" : "not approvable"}.
            </h1>
            <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-dim">
              {passed} of {pack.checks.length} checks passed on the simulated company <span className="text-ink">{pack.profile}</span> (seed{" "}
              <span className="num">{pack.seed}</span>), against its parent policy <span className="num text-ink">{pack.parent ?? "v0"}</span>. Every number below is
              measured by running the books on fresh clones against a hidden answer key; none is typed in.
              {pack.recorded_at && <> This pack was recorded on {new Date(pack.recorded_at).toLocaleDateString()} and served from the cache.</>}
            </p>

            <Section title="The verdict in numbers">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
                    <th className="py-2 pr-4 font-semibold"></th>
                    <th className="num py-2 pr-4 text-right font-semibold">{before?.policy ?? "before"}</th>
                    <th className="num py-2 text-right font-semibold">{after?.policy ?? pack.version}</th>
                  </tr>
                </thead>
                <tbody>
                  <Row label="Attack success on held-out variants" before={before?.attack_success_rate} after={after?.attack_success_rate} fmt={(n) => pct(n)} />
                  <Row label="Exposure" before={before?.exposure} after={after?.exposure} fmt={(n) => usd(n, { cents: false })} />
                  <Row label="Violating sequences found by search" before={before?.violations_found} after={after?.violations_found} fmt={String} />
                  <Row label="Legitimate payments blocked" before={before?.legit_blocked} after={after?.legit_blocked} fmt={String} />
                  <Row label="False positive rate" before={before?.false_positive_rate} after={after?.false_positive_rate} fmt={(n) => pct(n, 1)} />
                  <Row label="Holds (friction)" before={before?.holds} after={after?.holds} fmt={String} />
                </tbody>
              </table>
              {after && (
                <p className="mt-3 text-xs text-faint">
                  Search depth {after.search_depth}, {after.sequences_explored.toLocaleString()} sequences explored, {after.legit_operations} legitimate operations run.
                </p>
              )}
            </Section>

            <Section title="The rule">
              {policy && policy.controls.length > 0 ? (
                <ul className="space-y-5">
                  {policy.controls.map((c, i) => {
                    const r = readRule(c);
                    return (
                      <li key={i}>
                        <h3 className="text-sm font-semibold text-ink">
                          {r.name} <span className="num text-[11px] font-normal text-faint">{c.template}</span>
                        </h3>
                        {r.gist && <p className="mt-1 text-[13px] italic leading-relaxed text-dim">{r.gist}</p>}
                        <ul className="mt-2 space-y-1.5">
                          {r.does.map((line, j) => (
                            <li key={j} className="flex gap-2 text-[13px] leading-relaxed text-ink">
                              <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-ok/70" />
                              <span>{line}</span>
                            </li>
                          ))}
                        </ul>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <ul className="num space-y-1 text-[13px] text-ink">
                  {pack.chosen.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              )}
              {pack.diff.length > 0 && (
                <pre className="num mt-5 overflow-x-auto rounded border border-line bg-panel p-3 text-[11px] leading-relaxed">
                  {pack.diff.map((line, i) => (
                    <div key={i} className={line.startsWith("+") ? "text-ok" : line.startsWith("-") ? "text-bad" : "text-dim"}>
                      {line}
                    </div>
                  ))}
                </pre>
              )}
            </Section>

            <Section title="The six checks">
              <ol className="space-y-4">
                {pack.checks.map((c) => (
                  <li key={c.number} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3">
                    <span className={cx("text-base font-bold leading-none", c.passed ? "text-ok" : "text-bad")}>{c.passed ? "✓" : "✗"}</span>
                    <div>
                      <div className="text-sm text-ink">
                        <span className="num text-faint">{c.number}.</span> {c.name}
                      </div>
                      <div className="mt-0.5 text-[12px] leading-relaxed text-faint">{CHECK_HELP[c.name]}</div>
                      <div className="num mt-1 text-[12px] text-dim">{c.detail}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </Section>

            {pack.counterexample && (
              <Section title="The attack that started it">
                <p className="text-[13px] leading-relaxed text-dim">
                  Found under <span className="num text-ink">{pack.counterexample.found_under}</span>, it moved{" "}
                  <span className="num text-ink">{usd(pack.counterexample.exposure)}</span> and broke {pack.counterexample.violated.join(", ")}.
                </p>
                <ol className="mt-3 space-y-1.5">
                  {pack.counterexample.moves.map((m, i) => (
                    <li key={i} className="flex gap-3 text-[13px]">
                      <span className="num w-4 shrink-0 text-faint">{i + 1}</span>
                      <span className="num text-ink">{moveLine(m)}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            {pack.candidates.length > 0 && (
              <Section title="What was tried before this held">
                <ol className="space-y-2">
                  {pack.candidates.map((c, i) => (
                    <li key={i} className="text-[12px] leading-relaxed">
                      <span className="num text-ink">{c.controls.join(" + ")}</span>
                      <span className="text-dim"> · {c.result}</span>
                      {c.lint.length > 0 && <span className="text-faint"> · lint: {c.lint.join("; ")}</span>}
                      <span className="text-faint"> · {c.source}</span>
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            <footer className="mt-12 border-t border-line pt-6 text-xs text-faint">
              {SITE.name} · {SITE.tagline}. Everything in this report ran on a simulated company; no real money moved. Verification{" "}
              <span className="num">{jobId}</span>.
            </footer>
          </main>
        )}
      </div>
    </div>
  );
}
