"use client";

import { cx, INVARIANTS, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { Verdict } from "./ui";

/** The bookkeeping checks: what a reviewer looking only at the books would see. */
const BOOK_CHECKS = ["INV-1", "INV-7", "INV-3", "INV-8", "INV-10"];

/** The counterexample: the figure that went astray, the word for it, and below, what the books
 * said against what the bank did. */
export function AttackVerdict() {
  const s = useWarRoom();
  const attack = s.attack;
  if (!attack) return null;
  const { violated, exposure } = attack.finding;
  const held = BOOK_CHECKS.filter((v) => !violated.includes(v));
  const booksClean = held.length === BOOK_CHECKS.length;
  const messages = s.replays.before?.result.violations.map((v) => v.message).slice(0, 3) ?? [];
  const hot = exposure > 0;

  return (
    <section aria-label="Attack verdict" className="shrink-0 bg-panel">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-5">
          <span className={cx("num text-[36px] font-semibold leading-none", hot ? "text-red" : "text-warn")}>
            {hot ? usd(exposure) : `${violated.length} checks`}
          </span>
          <div className="max-w-[22rem] leading-tight">
            {hot ? (
              <>
                <div className="text-[14px] font-medium text-ink">went to the wrong account</div>
                <div className="text-[12.5px] text-dim">
                  {booksClean ? "while every entry in the books balanced." : `and ${violated.length} checks broke.`}
                </div>
              </>
            ) : (
              <>
                <div className="text-[14px] font-medium text-ink">broke, but no money was exposed</div>
                <div className="num text-[12.5px] text-dim">{violated.join(", ")}</div>
              </>
            )}
          </div>
        </div>
        <Verdict tone={hot ? "red" : "warn"} size="lg" land className="ml-auto">
          {hot ? "misdirected" : "broken"}
        </Verdict>
      </div>

      <div className="grid grid-cols-1 border-t border-line md:grid-cols-2">
        <div className="border-line px-4 py-2 text-[12px] text-dim md:border-r" title={held.map((v) => INVARIANTS[v]).join("\n")}>
          Books: <span className="num">{held.length}</span> of <span className="num">{BOOK_CHECKS.length}</span> bookkeeping checks pass
        </div>
        <ul className="px-4 py-2 text-[12px]">
          {violated.map((v) => (
            <li key={v} className="text-ink">
              <span className="num text-red">{v}</span> {INVARIANTS[v]}
            </li>
          ))}
          {messages.map((m, i) => (
            <li key={i} className="text-dim">
              {m}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
