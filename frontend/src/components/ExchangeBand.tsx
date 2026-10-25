"use client";

// The exchange: how the two agents actually work together, drawn as one thread.
// Vandal's lane runs along the top in red, Guard's along the bottom in blue. The
// seven steps of the loop sit on their owner's lane, and the thread crosses lanes
// exactly twice — when a copy of the books goes down into the sandbox, and when
// the proven rule comes back up for a human to approve. Done segments are inked,
// the current step rings, everything ahead stays faint. Click a step to open its side.

import { cx } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { useLoop } from "./TopBar";

const LANE_Y = { red: 22, blue: 58 } as const;
const BAND_H = 80;

/** Center of step i as a percentage of the band's width. */
const px = (i: number, n: number) => ((i + 0.5) / n) * 100;

export function ExchangeBand() {
  const setView = useWarRoom((s) => s.setView);
  const { steps, now } = useLoop();
  const n = steps.length;

  return (
    <nav
      aria-label="How Vandal and Guard work together"
      className="relative shrink-0 border-t border-line bg-bg"
      style={{ height: BAND_H }}
    >
      {/* lane names */}
      <div className="num pointer-events-none absolute left-3 text-[10px] font-semibold uppercase tracking-[0.16em] leading-none text-red" style={{ top: LANE_Y.red - 5 }}>
        Vandal
      </div>
      <div className="num pointer-events-none absolute left-3 text-[10px] font-semibold uppercase tracking-[0.16em] leading-none text-blue" style={{ top: LANE_Y.blue - 5 }}>
        Guard
      </div>

      {/* the thread */}
      <svg aria-hidden className="absolute inset-y-0 right-0" style={{ left: 64, width: "calc(100% - 76px)", height: BAND_H }}>
        {/* faint lane rails */}
        <line x1="0%" y1={LANE_Y.red} x2="100%" y2={LANE_Y.red} stroke="var(--color-line)" strokeWidth={1} />
        <line x1="0%" y1={LANE_Y.blue} x2="100%" y2={LANE_Y.blue} stroke="var(--color-line)" strokeWidth={1} />
        {steps.slice(0, -1).map((st, i) => {
          const nx = steps[i + 1];
          const inked = st.done;
          const color = nx.side === "red" ? "var(--color-red)" : "var(--color-blue)";
          return (
            <line
              key={st.n}
              x1={`${px(i, n)}%`}
              y1={LANE_Y[st.side]}
              x2={`${px(i + 1, n)}%`}
              y2={LANE_Y[nx.side]}
              stroke={inked ? color : "var(--color-faint)"}
              strokeWidth={inked ? 1.5 : 1}
              strokeDasharray={inked ? undefined : "2 4"}
            />
          );
        })}
      </svg>

      {/* what crosses between the lanes — the only words the band needs */}
      <div className="pointer-events-none absolute inset-y-0 right-0 max-md:hidden" style={{ left: 64, width: "calc(100% - 76px)" }}>
        {steps.slice(0, -1).map((st, i) => {
          const nx = steps[i + 1];
          if (st.side === nx.side) return null;
          const down = nx.side === "red";
          return (
            <span
              key={st.n}
              className={cx("num absolute -translate-x-1/2 text-[10px] uppercase tracking-[0.08em] leading-none", down ? "text-red" : "text-blue", !st.done && "opacity-50")}
              style={{ left: `${(px(i, n) + px(i + 1, n)) / 2}%`, top: (LANE_Y.red + LANE_Y.blue) / 2 - 5 }}
            >
              {down ? "a copy of the books" : "the proven rule"}
            </span>
          );
        })}
      </div>

      {/* the steps */}
      <div className="absolute inset-y-0 right-0" style={{ left: 64, width: "calc(100% - 76px)" }}>
        {steps.map((st, i) => {
          const red = st.side === "red";
          const current = now?.n === st.n;
          const on = st.done || current;
          return (
            <button
              key={st.n}
              onClick={() => void setView(st.side)}
              aria-current={current ? "step" : undefined}
              title={`${red ? "Vandal" : "Guard"}: ${st.next}`}
              className={cx("group absolute flex w-16 -translate-x-1/2 flex-col items-center", on ? (red ? "text-red" : "text-blue") : "text-faint")}
              style={{ left: `${px(i, n)}%`, top: LANE_Y[st.side] - 6 }}
            >
              <span
                className={cx(
                  "relative block size-3 rounded-full border-[1.5px] border-current bg-bg",
                  st.done && (red ? "bg-red" : "bg-blue"),
                  current && "ring",
                )}
              />
              <span className={cx("num mt-1 text-[9.5px] uppercase tracking-[0.12em] leading-none group-hover:underline", current ? "font-semibold" : st.done ? "text-ink" : "text-faint")}>
                {st.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
