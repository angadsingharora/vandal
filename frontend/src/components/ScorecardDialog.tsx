"use client";

import { useEffect, useState } from "react";
import { cx, pct, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import type { Scorecard } from "@/lib/types";
import { Button, Modal, Spinner, Table, td } from "./ui";

const ROWS: { label: string; get: (s: Scorecard) => string }[] = [
  { label: "Sequences explored", get: (s) => s.sequences_explored.toLocaleString() },
  { label: "Violations found", get: (s) => String(s.violations_found) },
  { label: "Attack success rate", get: (s) => pct(s.attack_success_rate) },
  { label: "Exposure", get: (s) => usd(s.exposure, { cents: false }) },
  { label: "Legit operations", get: (s) => String(s.legit_operations) },
  { label: "Legit failed", get: (s) => String(s.legit_failed) },
  { label: "Legit blocked", get: (s) => String(s.legit_blocked) },
  { label: "Holds (friction)", get: (s) => String(s.holds) },
  { label: "False-positive rate", get: (s) => pct(s.false_positive_rate, 1) },
  { label: "Broken invariants", get: (s) => s.broken_invariants.join(", ") || "none" },
  { label: "Extraction accuracy", get: (s) => pct(s.extraction_accuracy) },
  { label: "GL coding accuracy", get: (s) => pct(s.gl_coding_accuracy) },
];

export function ScorecardDialog({ onClose }: { onClose: () => void }) {
  const s = useWarRoom();
  const names = s.policies.map((p) => p.name);
  const [picked, setPicked] = useState<string[]>(() => ["v0", s.appliedPolicy ?? "v1"].filter((p) => names.includes(p)));
  const data = s.metrics.data;
  const cards = data ? picked.filter((p) => data.scorecards[p]).map((p) => data.scorecards[p]) : [];
  const classes = [...new Set(cards.flatMap((c) => Object.keys(c.attack_success)))].sort();

  useEffect(() => {
    if (!data && picked.length) void s.loadMetrics(picked);
  }, []); // once, when the dialog opens

  const toggle = (p: string) => setPicked((xs) => (xs.includes(p) ? xs.filter((x) => x !== p) : [...xs, p]));

  return (
    <Modal title="Scorecard" onClose={onClose} wide>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {names.map((p) => (
          <label key={p} className="flex items-center gap-1.5 text-[12px]">
            <input type="checkbox" checked={picked.includes(p)} onChange={() => toggle(p)} className="accent-blue" />
            <span className="num">{p}</span>
          </label>
        ))}
        <Button tone="blue" onClick={() => s.loadMetrics(picked)} busy={s.metrics.phase === "running"} disabled={!picked.length}>
          Score
        </Button>
        <span className="text-[11px] text-dim" title="The evidence pack has full-depth numbers.">
          Scored at search depth {data?.depth ?? 1} to stay interactive.
        </span>
      </div>
      {s.metrics.phase === "running" && !data && (
        <div className="flex items-center gap-2 text-[12px] text-dim">
          <Spinner /> Running held-out variants and regression.
        </div>
      )}
      {cards.length > 0 && (
        <Table head={["", ...cards.map((c) => <span key={c.policy} className="num">{c.policy}</span>)]}>
          {ROWS.map((row) => (
            <tr key={row.label}>
              <td className={cx(td, "text-dim")}>{row.label}</td>
              {cards.map((c) => (
                <td key={c.policy} className={cx(td, "num")}>
                  {row.get(c)}
                </td>
              ))}
            </tr>
          ))}
          {classes.length > 0 && (
            <tr>
              <td className={cx(td, "pt-3 text-dim")} colSpan={cards.length + 1} title="Succeeded / attempted held-out variants">
                Attacks through, by threat class
              </td>
            </tr>
          )}
          {classes.map((k) => (
            <tr key={k}>
              <td className={cx(td, "pl-5 text-dim")}>{k.replaceAll("_", " ")}</td>
              {cards.map((c) => {
                const r = c.attack_success[k];
                const tone = !r || r.attempts === 0 ? "text-faint" : r.succeeded > 0 ? "text-red" : "text-blue";
                return (
                  <td key={c.policy} className={cx(td, "num", tone)}>
                    {r && r.attempts > 0 ? `${r.succeeded}/${r.attempts}` : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </Table>
      )}
      {cards.some((c) => c.notes.length) && (
        <ul className="mt-3 space-y-0.5 text-[11px] text-dim">
          {cards.flatMap((c) =>
            c.notes.map((n, i) => (
              <li key={`${c.policy}-${i}`}>
                <span className="num">{c.policy}</span>: {n}
              </li>
            )),
          )}
        </ul>
      )}
    </Modal>
  );
}
