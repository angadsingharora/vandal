"use client";

import { cx, INVARIANTS, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Link } from "@/lib/types";
import { Badge, Empty, Panel, SideTag, Spinner } from "./ui";

const MARK: Record<Link["status"], { icon: string; style: string; label: string }> = {
  covered: { icon: "✓", style: "border-ok/40 text-ok", label: "covered" },
  uncovered: { icon: "✗", style: "border-bad bg-bad/10 text-bad shadow-[0_0_0_1px_var(--color-bad)]", label: "uncovered" },
  pending: { icon: "…", style: "border-line text-faint", label: "pending" },
};

function fact(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function ChainView() {
  const s = useWarRoom();
  const { chain, diagnosis } = s;
  const d = diagnosis.data;
  const showingDiagnosis = d && chain.payment === d.payment && chain.runId === null;
  const firstBroken = chain.data?.links.find((l) => l.status === "uncovered");

  return (
    <Panel
      title={
        <>
          Authorization chain{" "}
          {chain.payment && <span className="num normal-case tracking-normal text-ink">· {chain.payment}</span>}
          {chain.data?.invoice && <span className="num normal-case tracking-normal text-faint"> for {chain.data.invoice}</span>}
        </>
      }
      tag={<SideTag side="blue" />}
      actions={showingDiagnosis && <Badge tone="bad">diagnosis</Badge>}
      className="min-h-[220px] lg:max-h-[46vh]"
    >
      {!chain.payment && (
        <Empty>Pick a payment, or diagnose a counterexample, to walk obligation → approval → execution → settlement → books.</Empty>
      )}
      {chain.payment && !chain.data && (
        <div className="flex items-center gap-2 p-3 text-xs text-dim">
          <Spinner /> building the chain…
        </div>
      )}
      {chain.data && (
        <div className="space-y-3 p-3">
          <ol className="grid grid-cols-1 gap-2 md:grid-cols-5">
            {chain.data.links.map((l, i) => {
              const m = MARK[l.status];
              return (
                <li key={l.name} className="relative flex">
                  <div className={cx("flex-1 rounded border p-2", m.style)}>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold uppercase tracking-wider">{l.name}</span>
                      <span aria-label={m.label} className="text-sm font-bold">
                        {m.icon}
                      </span>
                    </div>
                    {l.gap && <div className="num mt-1 text-[11px] font-semibold">{l.gap}</div>}
                    {l.reason && <p className="mt-1 text-[11px] leading-snug text-ink/80">{l.reason}</p>}
                    {l.entities.length > 0 && (
                      <div className="num mt-1.5 flex flex-wrap gap-1 text-[10px] text-dim">
                        {l.entities.map((id) => (
                          <span key={id} className="rounded-sm bg-raised px-1">
                            {id}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {i < chain.data!.links.length - 1 && (
                    <span aria-hidden className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 text-faint md:block">
                      →
                    </span>
                  )}
                </li>
              );
            })}
          </ol>

          {firstBroken && Object.keys(firstBroken.facts).length > 0 && (
            <details className="text-[11px]">
              <summary className="cursor-pointer text-dim">Facts Blue evaluated at {firstBroken.name}</summary>
              <dl className="num mt-1 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5">
                {Object.entries(firstBroken.facts).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-faint">{k}</dt>
                    <dd className="break-all text-ink">{fact(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}

          {showingDiagnosis && (
            <div className="rounded border border-bad/40 bg-bad/5 p-2.5">
              <div className="text-[10px] uppercase tracking-wider text-bad">Root cause · {d.gap} at {d.link}</div>
              <p className="mt-1 text-sm text-ink">{d.reason}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11px] text-dim">
                {d.violated.map((v) => (
                  <span key={v} title={INVARIANTS[v]}>
                    <Badge tone="bad">{v}</Badge>
                  </span>
                ))}
                <span className="num ml-1">exposure {usd(d.exposure)}</span>
                {d.also.length > 0 && <span>· also uncovered: {d.also.join(", ")}</span>}
              </div>
              <div className="num mt-1 text-[10px] text-faint">cites {d.cites.join(" ")}</div>
            </div>
          )}
          {diagnosis.phase === "done" && !d && diagnosis.reason && <p className="text-xs text-dim">{diagnosis.reason}</p>}
        </div>
      )}
    </Panel>
  );
}
