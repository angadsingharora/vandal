"use client";

import { useEffect, useState } from "react";
import { cx } from "@/lib/format";
import { Chip, Cta, Hero } from "./bits";

/* The Weave: the tear stays on screen. Each CEGIS candidate is a blue thread woven across it;
   the spider crawls again against it. A thread that gets beaten snaps and goes to the refuted
   pile with its counterexample; one that holds thickens. Verification is six anchors the final
   thread is tied to. Approval is a human pulling it taut. Static data, animated locally. */

const CANDIDATES = [
  { id: "T2", name: "T2 ApprovalBinding", params: "bound_fields=[amount, payee_account] on_mismatch=hold", by: "Claude", fate: "snap", why: "search beat it in 1 move: change_request@0, before approval → INV-4, INV-5" },
  { id: "T2b", name: "T2 ApprovalBinding", params: "bound_fields=[payee_account] on_mismatch=reapprove", by: "Claude", fate: "snap", why: "same counterexample: the change arrives before anything is approved" },
  { id: "T1v", name: "T2 + T1 VerifiedAccountChange", params: "accepted_channels=[phone_outbound, video]", by: "Claude", fate: "lint", why: "spoofable: this attacker clones voice and spoofs caller id, so video can't verify" },
  { id: "T1", name: "T2 + T1 VerifiedAccountChange", params: "accepted_channels=[phone_outbound] contact_as_of=before_request", by: "Claude", fate: "hold", why: "no violation within depth 3 (34,676 sequences) · 9 holds, 0 blocks on legitimate operations" },
] as const;

const ANCHORS = [
  { id: "replay", label: "replay", detail: "counterexample held" },
  { id: "research", label: "re-search", detail: "no violation within depth 3" },
  { id: "variants", label: "variants", detail: "0 of 40 held-out variants got through" },
  { id: "regression", label: "regression", detail: "25 of 25 legitimate cases passed" },
  { id: "legit", label: "legit ops", detail: "80 invoices paid · 0 holds · 0 blocks" },
  { id: "invariants", label: "invariants", detail: "every run clean" },
];

const CX = 300;
const CY = 230;

export function Weave() {
  const [step, setStep] = useState(0); // candidates woven so far
  const [anchors, setAnchors] = useState(0);
  const [taut, setTaut] = useState(false);
  const [weaving, setWeaving] = useState(false);

  useEffect(() => {
    if (!weaving) return;
    if (step < CANDIDATES.length) {
      const t = setTimeout(() => setStep((s) => s + 1), 1500);
      return () => clearTimeout(t);
    }
    if (anchors < ANCHORS.length) {
      const t = setTimeout(() => setAnchors((a) => a + 1), 500);
      return () => clearTimeout(t);
    }
    setWeaving(false);
  }, [weaving, step, anchors]);

  const start = () => {
    setStep(0);
    setAnchors(0);
    setTaut(false);
    setWeaving(true);
  };
  const survivor = step >= CANDIDATES.length;
  const refuted = CANDIDATES.slice(0, step).filter((c) => c.fate !== "hold");

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="glass flex flex-wrap items-center gap-2 rounded-xl p-3">
          <label className="flex items-center gap-1.5 text-[11px] text-dim">
            depth
            <select className="num h-8 rounded-lg border border-line bg-bg px-2 text-xs text-ink" defaultValue="3">
              {[1, 2, 3].map((d) => <option key={d}>{d}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-dim">
            <input type="checkbox" className="accent-blue" /> no LLM
          </label>
          <Cta big tone="blue" onClick={start} busy={weaving} className="ml-auto">
            {step === 0 ? "Weave a control" : weaving ? "weaving…" : "Weave again"}
          </Cta>
        </div>
        <Hero label="Candidates" value={step} sub={`${refuted.length} refuted`} tone="blue" />
        <Hero label="Anchors set" value={`${anchors}/6`} sub="replay · re-search · variants · regression · legit ops · invariants" tone={anchors === 6 ? "ok" : "ink"} />
        <Hero label="Policy" value={taut ? "v1-synth" : survivor ? "pending" : "v0"} tone={taut ? "ok" : "dim"} glow={taut ? "ok" : undefined} sub={taut ? "applied to Blue · approved by U-CTRL" : survivor ? "waiting in the inbox" : "nothing woven yet"} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.25fr_1fr]">
        <div className="glass relative overflow-hidden rounded-xl">
          <svg viewBox="0 0 600 470" className="h-auto w-full" role="img" aria-label="The tear with candidate threads woven across it and six anchors around it">
            {/* the tear: center to the torn node */}
            <circle cx={CX} cy={CY} r={150} fill="none" stroke="#1c2640" />
            <circle cx={CX} cy={CY} r={9} fill="#37c6ff" />
            <line x1={CX} y1={CY} x2={CX} y2={CY - 150} stroke="#ff3b5c" strokeWidth={2.5} strokeDasharray="10 6" className={cx(!taut && "fray")} opacity={taut ? 0.25 : 1} />
            <circle cx={CX} cy={CY - 150} r={7} fill="#ff3b5c" className={cx(!taut && "ring-red")} />
            <text x={CX + 14} y={CY - 150} fill="#ff7a8f" fontSize="11" className="num">the tear · $40,000.00</text>

            {/* anchors on the ring */}
            {ANCHORS.map((a, i) => {
              const ang = (i / ANCHORS.length) * Math.PI * 2 - Math.PI / 2 + Math.PI / 6;
              const x = CX + 190 * Math.cos(ang);
              const y = CY + 190 * Math.sin(ang);
              const set = i < anchors;
              return (
                <g key={a.id}>
                  {set && <line x1={CX} y1={CY - 75} x2={x} y2={y} stroke="#5cf2a8" strokeOpacity={0.5} strokeWidth={1.2} className="draw" />}
                  <circle cx={x} cy={y} r={12} fill="#0d1222" stroke={set ? "#5cf2a8" : "#27345a"} strokeWidth={2} className={cx(set && "tick")} />
                  <text x={x} y={y + 4} textAnchor="middle" fill={set ? "#5cf2a8" : "#56627f"} fontSize="11" fontWeight="700">{set ? "✓" : i + 1}</text>
                  <text x={x} y={y + 28} textAnchor="middle" fill={set ? "#e6ecfa" : "#56627f"} fontSize="10" fontWeight="600">{a.label}</text>
                </g>
              );
            })}

            {/* woven threads across the tear */}
            {CANDIDATES.slice(0, step).map((c, i) => {
              const y = CY - 115 + i * 26;
              const sag = taut && c.fate === "hold" ? 0 : c.fate === "hold" ? 14 : 0;
              const d = `M${CX - 90},${y} Q${CX},${y + sag} ${CX + 90},${y}`;
              if (c.fate === "hold") {
                return (
                  <g key={c.id}>
                    <path d={d} fill="none" stroke="#37c6ff" strokeWidth={taut ? 6 : 2} strokeLinecap="round" className={cx(!taut && "thicken")} strokeDasharray={taut ? undefined : "0"} />
                    <text x={CX + 98} y={y + 4} fill="#8fe3ff" fontSize="10" className="num">{c.id} holds{taut ? " · taut" : " · slack until approved"}</text>
                  </g>
                );
              }
              return (
                <g key={c.id}>
                  <path d={d} fill="none" stroke={c.fate === "lint" ? "#c99bff" : "#37c6ff"} strokeWidth={2} className="snap" />
                  <text x={CX + 98} y={y + 4} fill={c.fate === "lint" ? "#c99bff" : "#ff7a8f"} fontSize="10" className="num">{c.id} {c.fate === "lint" ? "rejected by lint" : "snapped"}</text>
                </g>
              );
            })}
            {/* the spider crawls against the latest thread */}
            {weaving && step > 0 && step <= CANDIDATES.length && (
              <g transform={`translate(${CX - 60},${CY - 115 + (step - 1) * 26 - 10})`}>
                <circle r={5} fill="#ff3b5c" />
                {[0, 1, 2].map((k) => <line key={k} x1={-8} y1={-4 + k * 4} x2={8} y2={-4 + k * 4} stroke="#ff3b5c" strokeWidth={1} />)}
              </g>
            )}
            <text x={20} y={455} fill="#56627f" fontSize="10">the tear stays on screen · each candidate is a thread across it · the spider crawls again against each one</text>
          </svg>
        </div>

        <div className="space-y-3">
          <div className="glass rounded-xl">
            <header className="flex items-center gap-2 border-b border-line px-4 py-2">
              <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-dim">The refuted pile</h3>
              <span className="num ml-auto text-[11px] text-faint">{refuted.length}</span>
            </header>
            <ul className="p-3">
              {refuted.length === 0 && <li className="py-5 text-center text-xs text-faint">Threads that snap land here, with what broke them.</li>}
              {refuted.map((c) => (
                <li key={c.id} className="rise mb-2 rounded-xl border border-line bg-raised/40 p-3">
                  <div className="flex items-center gap-2">
                    <span className="num text-sm font-semibold text-ink">{c.name}</span>
                    <Chip tone={c.fate === "lint" ? "esc" : "red"}>{c.fate === "lint" ? "lint" : "beaten"}</Chip>
                    <Chip className="ml-auto">proposed by {c.by}</Chip>
                  </div>
                  <div className="num mt-1 text-[11px] text-dim">{c.params}</div>
                  <div className="mt-1 text-[12px] text-ink/80">{c.why}</div>
                </li>
              ))}
            </ul>
          </div>

          {survivor && (
            <div className={cx("glass rise rounded-xl p-4", taut ? "glow-ok" : "glow-blue")}>
              <div className="flex items-center gap-2">
                <Chip tone="ok">holds</Chip>
                <span className="num text-sm font-semibold text-ink">{CANDIDATES[3].name}</span>
              </div>
              <div className="num mt-1 text-[11px] text-dim">{CANDIDATES[3].params}</div>
              <div className="mt-1 text-[12px] text-ink/80">{CANDIDATES[3].why}</div>
              <ul className="mt-3 grid grid-cols-2 gap-1 text-[11px]">
                {ANCHORS.map((a, i) => (
                  <li key={a.id} className={cx("flex items-center gap-1.5", i < anchors ? "text-ok" : "text-faint")}>
                    <span>{i < anchors ? "✓" : "○"}</span> {a.label} <span className="text-dim">· {a.detail}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Cta big tone={taut ? "ghost" : "ok"} disabled={anchors < 6 || taut} onClick={() => setTaut(true)}>
                  {taut ? "Applied to Blue · v1-synth" : "Pull the thread taut · approve as Controller"}
                </Cta>
                <Cta tone="ghost" disabled>Operator tries to approve</Cta>
                <span className="text-[11px] text-faint">{taut ? "a second person signed it; the synthesizer and the Operator can't" : "slack until the inbox approves; the policy stays unapplied"}</span>
              </div>
            </div>
          )}

          {taut && (
            <div className="rise grid grid-cols-2 gap-2">
              <div className="glass rounded-xl border-red/40 p-3">
                <div className="text-[10px] uppercase tracking-wider text-dim">before · v0</div>
                <div className="num text-xl font-bold text-red2">$40,000.00</div>
                <div className="text-[11px] text-dim">BROKEN · INV-2, INV-4, INV-5</div>
              </div>
              <div className="glass glow-ok rounded-xl p-3">
                <div className="text-[10px] uppercase tracking-wider text-dim">after · v1-synth</div>
                <div className="num text-xl font-bold text-ok">$0.00</div>
                <div className="text-[11px] text-dim">HELD · the spider crawled again and found no tear</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
