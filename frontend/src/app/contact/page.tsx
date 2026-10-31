import type { Metadata } from "next";
import Link from "next/link";
import { linkClass, SitePage, SiteSection } from "@/components/site/SiteShell";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Contact",
  description: "Talk to the Vandal team about a pilot, a demo, or the design.",
};

const pilot = `mailto:${SITE.email}?subject=${encodeURIComponent("Vandal pilot")}&body=${encodeURIComponent(
  "Hi,\n\nWe are handing accounts payable to an agent (or about to). Here is our setup:\n\n- Company and size:\n- AP volume (invoices per month):\n- The agent or tooling we use:\n- What worries us most:\n\n",
)}`;
const demo = `mailto:${SITE.email}?subject=${encodeURIComponent("Vandal demo")}`;

export default function ContactPage() {
  return (
    <SitePage current="/contact" title="Talk to us." lede="If your company is handing payables to an agent, or about to, we want to hear what the setup looks like and what worries you. We reply to every message.">
      <SiteSection title="Three ways in">
        <div className="grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-3">
          <div className="bg-panel p-5">
            <h3 className="text-sm font-semibold text-ink">Run a pilot</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Point Vandal at a description of your company: approval rules, vendors, what the attacker could do. We run Strike on
              the twin and walk you through what it finds and the controls it proposes.
            </p>
            <a href={pilot} className="mt-4 inline-flex h-9 items-center rounded border border-blue/60 bg-blue/15 px-4 text-sm font-semibold text-blue hover:bg-blue/25">
              Request a pilot
            </a>
          </div>
          <div className="bg-panel p-5">
            <h3 className="text-sm font-semibold text-ink">See a demo</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              Twenty minutes, live, on the simulated company: an attack found, a control synthesized, the attack replayed and held.
              Or run it yourself right now.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <a href={demo} className="inline-flex h-9 items-center rounded border border-line bg-raised px-4 text-sm font-semibold text-ink hover:border-dim">
                Book a demo
              </a>
              <Link href="/" className={`${linkClass} text-[13px]`}>
                Start the demo yourself
              </Link>
            </div>
          </div>
          <div className="bg-panel p-5">
            <h3 className="text-sm font-semibold text-ink">Read or contribute</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
              The design, the tests, and the scorecard from a real run are all in the open. Questions about the approach belong in
              an issue, where the answer helps the next reader too.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <a href={`${SITE.github}/issues/new`} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center rounded border border-line bg-raised px-4 text-sm font-semibold text-ink hover:border-dim">
                Open an issue
              </a>
              <a href={SITE.github} target="_blank" rel="noreferrer" className={`${linkClass} text-[13px]`}>
                Source on GitHub
              </a>
            </div>
          </div>
        </div>
      </SiteSection>

      <SiteSection title="Email">
        <p className="text-[15px] text-ink">
          <a href={`mailto:${SITE.email}`} className={`${linkClass} num`}>
            {SITE.email}
          </a>
        </p>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-dim">
          Anything else: partnerships, press, a question about whether your setup fits. Say what you are running and what you are
          worried about, and we will tell you plainly whether Vandal helps.
        </p>
      </SiteSection>
    </SitePage>
  );
}
