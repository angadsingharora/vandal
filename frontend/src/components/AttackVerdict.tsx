"use client";

import { cx, INVARIANTS, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";

/** The bookkeeping checks: what a reviewer looking only at the books would see. */
const BOOK_CHECKS = ["INV-1", "INV-7", "INV-3", "INV-8", "INV-10"];

/** The counterexample, told as the gap between what the books say and where the money went:
 * "your books can balance perfectly while the money goes to the wrong person". */
export function AttackVerdict() {
  const s = useWarRoom();
  const attack = s.attack;
  if (!attack) return null;
  const { violated, exposure } = attack.finding;
  const held = BOOK_CHECKS.filter((v) => !violated.includes(v));
  const booksClean = held.length === BOOK_CHECKS.length;
  const messages = s.replays.before?.result.violations.map((v) => v.message).slice(0, 3) ?? [];

  const verdict = exposure > 0
    ? booksClean
      ? `The books balance. ${usd(exposure)} went to the wrong account.`
      : `${violated.length} checks broke. ${usd(exposure)} exposed.`
    : `${violated.length} checks broke, no money exposed.`;

  return (
    <section aria-label="Attack verdict" className="shrink-0 bg-panel">
      <div className="grid grid-cols-1 gap-px bg-line md:grid-cols-2">
        <div className="bg-panel p-3">
          <div className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-faint">What the books say</div>
          <ul className="num space-y-0.5 text-[11px]">
            {held.map((v) => (
              <li key={v} className="flex gap-2">
                <span className="text-ok">✓</span>
                <span className="text-dim">{INVARIANTS[v]}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-panel p-3">
          <div className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-faint">What actually happened</div>
          <ul className="num space-y-0.5 text-[11px]">
            {violated.map((v) => (
              <li key={v} className="flex gap-2">
                <span className="text-bad">✗</span>
                <span className="text-ink">
                  <span className="text-bad">{v}</span> {INVARIANTS[v]}
                </span>
              </li>
            ))}
            {messages.map((m, i) => (
              <li key={i} className="pl-4 text-dim">
                {m}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div
        className={cx(
          "num border-l-2 border-t border-t-line px-3 py-2 text-xs font-semibold uppercase tracking-wider",
          exposure > 0 ? "border-l-bad bg-bad/10 text-bad" : "border-l-warn bg-warn/10 text-warn",
        )}
      >
        {verdict}
      </div>
    </section>
  );
}
