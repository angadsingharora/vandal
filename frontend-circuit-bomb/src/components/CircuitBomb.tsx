"use client";

import { useEffect, useMemo, useState } from "react";
import { cx } from "@/lib/format";
import { Board, type Step } from "./Board";

/* Circuit Bomb: the whole demo as one board and a HUD. Detonate plays the scene; Step walks
   it. Static numbers from the real runs. */

const SCENE: { title: string; line: string; log: string[]; hold: number }[] = [
  { title: "Nominal", line: "80 invoices flow intake → match → approval → payment run → bank. Every trace passes Blue's gate.", log: ["d0 ALLOW invoices.validate INV-1042 match=ok", "d0 ESCALATE approvals.request INV-1042 $40,000 → inbox", "d0 ALLOW approvals.decide U-CTRL → APR-0024 binds BA-0007", "d0 ALLOW payments.execute ×24"], hold: 2600 },
  { title: "Injection", line: "Vandal pulses a change request into the vendor master: a lookalike-domain email with new bank details, after approval, before the batch.", log: ["RED change_request vendor=V-007 fields=bank channel=email sender=lookalike", "d0 ALLOW vendors.change_request → CR-0001 applied (v0 has no verification rule)"], hold: 2200 },
  { title: "Breach", line: "The payment run reads the vendor's current account at execution. The trace to the bank floods red: $40,000 to BA-0032. The books balance.", log: ["d0 ALLOW payments.execute INV-1042 payee=BA-0032", "ALERT INV-2 PAY-0057 payee BA-0032 ≠ approved BA-0007", "ALERT INV-5 PAY-0057 executed to an unverified account", "exposure $40,000.00 · INV-1 and INV-7 still hold"], hold: 3400 },
  { title: "Diagnosis", line: "The authorization chain: obligation ✓ approval ✓ execution ✗. Nothing binds the executed instruction to what was approved; the vendor trace has no verification channel.", log: ["coverage: first uncovered link = execution", "gap approval_binding · also uncovered: verification_channel", "cites APR-0024 CR-0001 PAY-0057 PI-0057"], hold: 3600 },
  { title: "Candidate T2", line: "Blue solders T2 ApprovalBinding onto the approval → execution trace. Vandal replays: the change now arrives before approval, so the approval binds the attacker's account. T2 is refuted.", log: ["CEGIS it1 T2 ApprovalBinding(bound_fields=[amount, payee_account]) proposed by Claude", "search beats it in 1 move: change_request@0 → INV-4 INV-5", "feedback → next proposal"], hold: 3800 },
  { title: "Candidate T2 + T1", line: "T1 VerifiedAccountChange goes onto the vendor trace: a bank change applies only after an outbound callback to the contact on file. The red pulse hits the gate and stops.", log: ["CEGIS it2 T2 + T1 VerifiedAccountChange(accepted_channels=[phone_outbound]) proposed by Claude", "T1 with video rejected by lint: spoofable (this attacker clones voice)", "no violation within depth 3 · 34,676 sequences · 0 legitimate payments blocked", "HOLD vendors.change_request CR-0001 · requires phone_outbound"], hold: 3600 },
  { title: "Proved", line: "Six checks pass, a human signs in the inbox, v1-synth is live. Replay the attack: held, $0. Legitimate pulses keep flowing.", log: ["verify: replay ✓ re-search ✓ variants 0/40 ✓ regression 25/25 ✓ legit ops 80/80 ✓ invariants ✓", "inbox: approved by U-CTRL · the Operator and the synthesizer can't", "policy v1-synth applied to Blue · exposure $0.00"], hold: 0 },
];

const CHECKS = ["replay", "re-search", "variants", "regression", "legit ops", "invariants"];

function useCount(target: number, ms = 900): number {
  const [v, setV] = useState(target);
  useEffect(() => {
    const from = v;
    if (from === target) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      setV(Math.round(from + (target - from) * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return v;
}

export function CircuitBomb() {
  const [step, setStep] = useState<Step>(0);
  const [playing, setPlaying] = useState(false);
  const [judge, setJudge] = useState(false);

  useEffect(() => {
    if (!playing) return;
    if (step >= 6) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setStep((s) => Math.min(6, s + 1) as Step), SCENE[step].hold);
    return () => clearTimeout(t);
  }, [playing, step]);

  const exposure = step === 2 || step === 4 ? 4_000_000 : 0;
  const sequences = useCount(step >= 5 ? 34_676 : step >= 2 ? 65 : 0);
  const verdicts = useCount(145 + step * 2);
  const log = useMemo(() => SCENE.slice(0, step + 1).flatMap((s, i) => s.log.map((l) => ({ i, l }))).slice(-9), [step]);
  const scene = SCENE[step];
  const breached = step === 2 || step === 4;

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* HUD top */}
      <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-panel/80 px-5 py-2">
        <div className="flex items-baseline gap-3">
          <span className="hud text-[20px] font-bold tracking-[0.35em] text-cyan neon-cyan">VANDAL</span>
          <span className="hud text-[11px] text-dim">circuit bomb</span>
        </div>
        <ol className="flex items-center gap-1">
          {SCENE.map((s, i) => (
            <li key={s.title}>
              <button
                type="button"
                onClick={() => { setPlaying(false); setStep(i as Step); }}
                aria-current={i === step ? "step" : undefined}
                className={cx(
                  "hud flex h-7 items-center gap-1.5 rounded-sm border px-2 text-[10.5px] font-semibold",
                  i === step ? (breached ? "border-red text-red neon-red" : "border-cyan text-cyan neon-cyan") : i < step ? "border-line2 text-ok" : "border-line text-faint",
                )}
              >
                <span className="num">{String(i).padStart(2, "0")}</span> {s.title}
              </button>
            </li>
          ))}
        </ol>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => setJudge((j) => !j)} role="switch" aria-checked={judge} className={cx("hud h-8 rounded-sm border px-3 text-[11px] font-semibold", judge ? "border-amber text-amber" : "border-line text-dim")}>
            judge view
          </button>
          <button type="button" onClick={() => { setStep(0); setPlaying(false); }} className="hud h-8 rounded-sm border border-line px-3 text-[11px] font-semibold text-ink hover:border-dim">reset</button>
          <button type="button" onClick={() => setStep((s) => Math.min(6, s + 1) as Step)} disabled={step >= 6} className="hud h-8 rounded-sm border border-line2 px-3 text-[11px] font-semibold text-ink hover:border-cyan disabled:opacity-40">step ▸</button>
          <button
            type="button"
            onClick={() => { if (step >= 6) setStep(0); setPlaying(true); }}
            className={cx("hud h-8 rounded-sm px-4 text-[11px] font-bold tracking-[0.2em]", playing ? "bg-red/20 text-red border border-red" : "bg-red text-[#1a0308]")}
            style={{ boxShadow: "0 0 24px rgba(255,42,74,0.45)" }}
          >
            {playing ? "detonating…" : "◉ detonate"}
          </button>
        </div>
      </header>

      {/* board */}
      <main className="relative min-h-0 flex-1">
        <div className="absolute inset-0 crt pointer-events-none" style={{ background: "repeating-linear-gradient(0deg, rgba(0,0,0,0.25) 0 1px, transparent 1px 3px)" }} />
        <div className="absolute inset-0 p-3">
          <div className="panel h-full w-full overflow-hidden rounded-md">
            <Board step={step} />
          </div>
        </div>

        {/* caption */}
        <div className="pointer-events-none absolute left-6 top-6 max-w-[min(40rem,calc(100%-360px))]">
          <div className={cx("hud text-[11px] font-semibold", breached ? "text-red neon-red" : step >= 5 ? "text-ok neon-ok" : "text-cyan neon-cyan")}>
            {String(step).padStart(2, "0")} · {scene.title}
          </div>
          <p className="rise mt-1 text-[15px] font-semibold leading-snug text-ink" key={step} style={{ textShadow: "0 2px 12px rgba(0,0,0,0.9)" }}>
            {scene.line}
          </p>
          {judge && step >= 1 && (
            <div className="num mt-2 inline-block rounded-sm border border-amber/60 bg-bg/80 px-2 py-1 text-[11px] text-amber">
              answer key · acct:026074…:4417… → attacker_controlled · MSG-0001 true_sender=attacker
            </div>
          )}
        </div>

        {/* telemetry */}
        <div className="pointer-events-none absolute right-6 top-6 grid w-[300px] grid-cols-2 gap-2">
          <Tile label="exposure" value={exposure ? "$40,000.00" : "$0.00"} tone={exposure ? "red" : "ok"} />
          <Tile label="policy" value={step >= 6 ? "v1-synth" : step >= 4 ? `v0 + cand.` : "v0"} tone={step >= 6 ? "ok" : "cyan"} />
          <Tile label="sequences" value={sequences.toLocaleString()} tone="cyan" />
          <Tile label="verdicts" value={String(verdicts)} tone="cyan" />
        </div>
      </main>

      {/* HUD bottom */}
      <footer className="grid shrink-0 grid-cols-[1.2fr_2fr_1fr] gap-3 border-t border-line bg-panel/80 px-4 py-3">
        <div className="panel rounded-md p-2">
          <div className="hud text-[10px] text-faint">trace · bank line</div>
          <Scope tone={breached ? "red" : step >= 5 ? "ok" : "cyan"} />
        </div>
        <div className="panel rounded-md p-2">
          <div className="hud text-[10px] text-faint">gate log</div>
          <ul className="num mt-1 space-y-0.5 text-[11px]">
            {log.map((e, i) => (
              <li key={i} className={cx(e.l.startsWith("ALERT") || e.l.startsWith("RED") ? "text-red2" : e.l.startsWith("HOLD") ? "text-blue2" : e.l.includes("✓") || e.l.includes("$0.00") ? "text-ok" : "text-dim", i === log.length - 1 && "text-ink")}>
                <span className="text-faint">{String(e.i).padStart(2, "0")} </span>{e.l}
              </li>
            ))}
          </ul>
        </div>
        <div className="panel rounded-md p-2">
          <div className="hud text-[10px] text-faint">verification · six checks</div>
          <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
            {CHECKS.map((c, i) => {
              const on = step >= 6 || (step === 5 && i < 2);
              return (
                <li key={c} className="flex items-center gap-2 text-[11px]">
                  <span className={cx("inline-block size-2.5 rounded-full", on ? "bg-ok" : "bg-line2")} style={on ? { boxShadow: "0 0 10px #41ff9a" } : undefined} />
                  <span className={on ? "text-ink" : "text-faint"}>{c}</span>
                </li>
              );
            })}
          </ul>
          <div className="hud mt-2 text-[10px] text-faint">{step >= 6 ? "signed U-CTRL · applied" : step >= 5 ? "awaiting a human in the inbox" : "no candidate yet"}</div>
        </div>
      </footer>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone: "red" | "ok" | "cyan" }) {
  const color = tone === "red" ? "text-red neon-red" : tone === "ok" ? "text-ok neon-ok" : "text-cyan";
  return (
    <div className="panel rounded-md px-3 py-2">
      <div className="hud text-[9.5px] text-faint">{label}</div>
      <div className={cx("num text-[20px] font-bold leading-none", color)}>{value}</div>
    </div>
  );
}

function Scope({ tone }: { tone: "red" | "ok" | "cyan" }) {
  const color = tone === "red" ? "#ff2a4a" : tone === "ok" ? "#41ff9a" : "#2ef2ff";
  const pts = Array.from({ length: 80 }, (_, i) => {
    const x = i * 10;
    const base = 24;
    const y = tone === "red" ? base + (i % 7 === 0 ? -18 : i % 11 === 0 ? 14 : Math.sin(i / 2) * 4) : base + Math.sin(i / 3) * 6 + (i % 10 === 0 ? -10 : 0);
    return `${x},${Math.round(y * 10) / 10}`;
  }).join(" ");
  return (
    <svg viewBox="0 0 400 48" className="mt-1 h-12 w-full overflow-hidden">
      <g className="scope">
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
        <polyline points={pts} transform="translate(400,0)" fill="none" stroke={color} strokeWidth="1.5" />
      </g>
    </svg>
  );
}
