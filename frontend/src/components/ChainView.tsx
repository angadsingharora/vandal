"use client";

import { cx, INVARIANTS, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Link } from "@/lib/types";
import { Badge, Panel, Spinner, Verdict } from "./ui";

const MARK: Record<Link["status"], { icon: string; style: string; label: string }> = {
  covered: { icon: "✓", style: "border-line text-ink", label: "covered" },
  uncovered: { icon: "✗", style: "border-red text-ink", label: "uncovered" },
  pending: { icon: "…", style: "border-line/50 text-faint", label: "pending" },
};

function fact(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** The authorization chain as five columns; the broken link carries the red rule. */
export function ChainView() {
  const s = useWarRoom();
  const { chain, diagnosis } = s;
  const d = diagnosis.data;
  const showingDiagnosis = d && chain.payment === d.payment && chain.runId === null;
  const firstBroken = chain.data?.links.find((l) => l.status === "uncovered");

  return (
    <Panel
      title="Diagnose"
      actions={
        <>
          {chain.payment && (
            <span className="num text-[11px] text-dim" title={chain.data?.invoice ? `Invoice ${chain.data.invoice}` : undefined}>
              {chain.payment}
            </span>
          )}
          {showingDiagnosis && <Verdict tone="red">diagnosis</Verdict>}
        </>
      }
      className={chain.payment ? "min-h-[220px] lg:max-h-[46vh]" : ""}
    >
      {!chain.payment && (
        <p className="px-3 py-2 text-[12px] text-dim">Diagnose a counterexample or click a payment to walk its authorization chain.</p>
      )}
      {chain.payment && !chain.data && (
        <div className="flex items-center gap-2 p-3 text-[12px] text-dim">
          <Spinner /> Building the chain
        </div>
      )}
      {chain.data && (
        <div className="space-y-4 p-3">
          <ol className="grid grid-cols-1 gap-3 md:grid-cols-5">
            {chain.data.links.map((l) => {
              const m = MARK[l.status];
              return (
                <li key={l.name} className={cx("min-w-0 border-l-2 pl-2", m.style)}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12.5px] font-medium capitalize">{l.name}</span>
                    <span aria-label={m.label} title={m.label} className={cx("num text-[12.5px]", l.status === "uncovered" && "text-red")}>
                      {m.icon}
                    </span>
                  </div>
                  {l.gap && <div className="num mt-0.5 text-[12px] text-red">{l.gap}</div>}
                  {l.reason && <p className="mt-0.5 text-[12px] leading-snug text-dim">{l.reason}</p>}
                  {l.entities.length > 0 && <div className="num mt-1 break-all text-[11px] text-dim">{l.entities.join(" ")}</div>}
                </li>
              );
            })}
          </ol>

          {firstBroken && Object.keys(firstBroken.facts).length > 0 && (
            <details className="text-[12px]">
              <summary className="cursor-pointer text-dim">Facts at {firstBroken.name}</summary>
              <dl className="num mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
                {Object.entries(firstBroken.facts).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-dim">{k}</dt>
                    <dd className="break-all text-ink">{fact(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}

          {showingDiagnosis && (
            <div className="border-l-2 border-red pl-3">
              <div className="text-[12.5px] font-medium text-red">
                Root cause <span className="num font-normal text-dim">{d.gap} at {d.link}</span>
              </div>
              <p className="mt-1 text-[13px] leading-snug text-ink">{d.reason}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-dim">
                {d.violated.map((v) => (
                  <Badge key={v} tone="bad" title={INVARIANTS[v]}>
                    {v}
                  </Badge>
                ))}
                <span className="num">exposure {usd(d.exposure)}</span>
                {d.also.length > 0 && <span>also uncovered {d.also.join(", ")}</span>}
              </div>
              <div className="num mt-1 text-[11px] text-dim">cites {d.cites.join(" ")}</div>
            </div>
          )}
          {diagnosis.phase === "done" && !d && diagnosis.reason && <p className="text-[12px] text-dim">{diagnosis.reason}</p>}
        </div>
      )}
    </Panel>
  );
}
