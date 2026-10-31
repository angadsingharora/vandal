import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@/lib/format";
import { NAV, SITE } from "@/lib/site";

/** The header the landing page and the company pages share: wordmark and three links. */
export function SiteHeader({ current, className }: { current: "/" | "/about" | "/contact"; className?: string }) {
  return (
    <header className={cx("flex items-baseline justify-between gap-6", className)}>
      <Link href="/" className="text-base font-semibold tracking-tight text-ink">
        {SITE.name}
      </Link>
      <nav aria-label="Site" className="flex items-baseline gap-5 text-xs">
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            aria-current={current === n.href ? "page" : undefined}
            className={cx("underline-offset-4 hover:text-ink hover:underline", current === n.href ? "text-ink" : "text-dim")}
          >
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={cx("flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-t border-line pt-6 text-xs text-faint", className)}>
      <span>
        {SITE.name} · {SITE.tagline}. Everything on this site runs on a simulated company; no real money moves.
      </span>
      <span className="flex items-baseline gap-4">
        <Link href="/about" className="underline-offset-4 hover:text-ink hover:underline">
          About
        </Link>
        <Link href="/contact" className="underline-offset-4 hover:text-ink hover:underline">
          Contact
        </Link>
      </span>
    </footer>
  );
}

/** A company page: the same column, header and footer as the landing, with a title. */
export function SitePage({ current, title, lede, children }: { current: "/about" | "/contact"; title: string; lede: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto w-full max-w-6xl px-6 py-8 sm:px-10 lg:py-12">
        <SiteHeader current={current} />
        <main className="mt-16 lg:mt-20">
          <h1 className="max-w-2xl text-4xl font-bold leading-[1.05] tracking-tight text-ink sm:text-5xl">{title}</h1>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-dim">{lede}</p>
          {children}
        </main>
        <SiteFooter className="mt-20" />
      </div>
    </div>
  );
}

/** A titled block on a company page. */
export function SiteSection({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cx("mt-14 border-t border-line pt-8", className)}>
      <h2 className="text-xs font-semibold uppercase tracking-wider text-faint">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

export const linkClass = "text-ink underline underline-offset-4 decoration-line hover:decoration-ink";
