import type { Metadata } from "next";
import Link from "next/link";
import { linkClass, SitePage, SiteSection } from "@/components/site/SiteShell";
import { cx } from "@/lib/format";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "About",
  description: "Why Vandal exists, what is real and what is simulated, what we can and cannot claim, and who is building it.",
};

// From the README's "What's real, what's simulated, and how we know".
const REAL: { real: string; simulated: string; how: string }[] = [
  {
    real: "A double-entry ledger, the financial invariants, the policy gate, bounded search, and CEGIS verification: deterministic code with tests.",
    simulated: "The company, its vendors, its bank accounts, and the money.",
    how: "Hidden oracle labels act as an answer key that no agent can read.",
  },
  {
    real: "Claude reading every document, proposing controls, and explaining decisions with citations.",
    simulated: "Callbacks, deepfakes, and counterparty agents, modelled as channel events with forgeable attributes. No synthetic media.",
    how: "Held-out variants the synthesizer never saw, plus a re-search under the new policy.",
  },
  {
    real: "The synthesizer proposing controls, and search refuting or accepting them.",
    simulated: "Bank behaviour and faults: timeouts, dropped acknowledgements, late feeds.",
    how: "The scorecard: before-and-after rates from actual runs.",
  },
  {
    real: "Replay of any recorded trace.",
    simulated: "Approvers, when no human is present.",
    how: "Replay-determinism tests in the backend suite.",
  },
];

// From the README's "What we can and can't claim".
const CLAIMS: { can: string; cant: string }[] = [
  { can: "No violating sequence of length ≤ k within the modelled actions and capabilities.", cant: "Mathematically proven safe." },
  { can: "The root cause is computed from the authorization chain.", cant: "Finds every possible failure." },
  { can: "The control was verified by replay, re-search, held-out variants, and regression.", cant: "Works on your real systems today." },
  { can: "Exposure, measured on the twin.", cant: "Losses prevented." },
  { can: "Synthesizes controls from a bounded template library.", cant: "Rewrites arbitrary financial software." },
];

const cell = "px-4 py-3 align-top text-[13px] leading-relaxed";

export default function AboutPage() {
  return (
    <SitePage
      current="/about"
      title="Finance agents are about to run the money. The controls were built for clerks."
      lede={SITE.what}
    >
      <SiteSection title="Why now">
        <div className="grid gap-8 sm:grid-cols-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">Agents are taking over accounts payable</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Reading invoices, matching purchase orders, updating vendor bank details, paying on schedule. The work is repetitive,
              well-documented, and expensive to do by hand, so it is going first.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">The controls assume a human is reading</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Three-way match, approval thresholds, callback policies. They were written for a clerk who might notice a lookalike
              domain. An agent that follows instructions faithfully follows forged ones too.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">Security has to attack itself</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Every change to an agent, a prompt, or a policy opens new paths. A control layer that cannot search for its own gaps
              will be wrong within a quarter. Vandal searches, fixes, proves, and only then enforces.
            </p>
          </div>
        </div>
      </SiteSection>

      <SiteSection title="How it works">
        <div className="grid gap-8 sm:grid-cols-3">
          <div>
            <h3 className="text-sm font-semibold text-blue">Vandal Guard</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Sits in the live path. Before any money moves it checks the action the agent is taking, a payment, a bank change, a
              refund, a journal entry, against an independent source of truth, then allows it, holds it, or escalates it to a
              human, and records the evidence.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-red">Vandal Strike</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Clones the company into a deterministic financial twin and searches for sequences of events that break the
              invariants. When it finds one, it computes the root cause from the authorization chain, synthesizes a control that
              closes the gap, and verifies it on fresh clones before anyone sees it.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-ink">The loop</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Every gap Strike finds becomes a control Guard enforces. Fixes go into Guard&apos;s rules, never into the agent: no
              retraining, no prompt edits. A human approves each rule. The protection holds whichever agent does the work.
            </p>
          </div>
        </div>
        <p className="mt-6 text-[13px] text-dim">
          <Link href="/" className={linkClass}>
            Watch the loop run
          </Link>{" "}
          on a simulated property manager, or open the workspace and point it at a company of your own description.
        </p>
      </SiteSection>

      <SiteSection title="What is real, what is simulated, and how we know">
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full min-w-[40rem] border-collapse bg-panel">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
                <th className="px-4 py-2.5 font-semibold">Real</th>
                <th className="px-4 py-2.5 font-semibold">Simulated</th>
                <th className="px-4 py-2.5 font-semibold">How we know it works</th>
              </tr>
            </thead>
            <tbody>
              {REAL.map((r) => (
                <tr key={r.real} className="border-b border-line last:border-b-0">
                  <td className={cx(cell, "text-ink")}>{r.real}</td>
                  <td className={cx(cell, "text-dim")}>{r.simulated}</td>
                  <td className={cx(cell, "text-dim")}>{r.how}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SiteSection>

      <SiteSection title="What we can and cannot claim">
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full min-w-[32rem] border-collapse bg-panel">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-faint">
                <th className="px-4 py-2.5 font-semibold text-ok">We can say</th>
                <th className="px-4 py-2.5 font-semibold text-bad">We do not say</th>
              </tr>
            </thead>
            <tbody>
              {CLAIMS.map((c) => (
                <tr key={c.can} className="border-b border-line last:border-b-0">
                  <td className={cx(cell, "text-ink")}>{c.can}</td>
                  <td className={cx(cell, "text-dim")}>{c.cant}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 max-w-2xl text-[13px] leading-relaxed text-dim">
          Every number on this site is measured by running the books on fresh clones against a hidden answer key. None is typed
          in. The scorecard from an actual run, and the tests behind it, are in the repository.
        </p>
      </SiteSection>

      <SiteSection title="Read the design">
        <ul className="grid gap-4 sm:grid-cols-3">
          {SITE.docs.map((d) => (
            <li key={d.href}>
              <a href={d.href} target="_blank" rel="noreferrer" className={cx(linkClass, "num text-[13px] font-semibold")}>
                {d.label}
              </a>
              <p className="mt-1 text-[13px] leading-relaxed text-dim">{d.what}</p>
            </li>
          ))}
        </ul>
      </SiteSection>

      <SiteSection title="Who is building it">
        <ul className="flex flex-wrap gap-x-10 gap-y-3">
          {SITE.founders.map((f) => (
            <li key={f.name} className="text-[15px] text-ink">
              {f.link ? (
                <a href={f.link} target="_blank" rel="noreferrer" className={linkClass}>
                  {f.name}
                </a>
              ) : (
                f.name
              )}
            </li>
          ))}
        </ul>
        <p className="mt-4 max-w-2xl text-[13px] leading-relaxed text-dim">
          Two people, one repository, and a demo you can run yourself.{" "}
          <Link href="/contact" className={linkClass}>
            Talk to us
          </Link>{" "}
          if your company is handing payables to an agent, or about to.
        </p>
      </SiteSection>
    </SitePage>
  );
}
