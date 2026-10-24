"use client";

import { useEffect, useMemo, useState } from "react";
import { cx } from "@/lib/format";
import { Board, type Step } from "./Board";

/* Circuit Bomb: one board, one scene, a quiet HUD. Static numbers from the real runs. */

const SCENE: { title: string; line: string; log: string[]; hold: number }[] = [
  { title: "Nominal", line: "80 invoices move along the bus: intake, match, approval, payment run, bank. Every trace passes Blue's gate.", log: ["d0 allow invoices.validate INV-1042 match=ok", "d0 escalate approvals.request INV-1042 $40,000 → inbox", "d0 allow approvals.decide U-CTRL · APR-0024 binds BA-0007", "d0 allow payments.execute ×24"], hold: 2600 },
  { title: "Injection", line: "Vandal connects at J1 and pulses a change request into the vendor master: a lookalike email with new bank details, after approval, before the batch.", log: ["red change_request vendor=V-007 fields=bank channel=email sender=lookalike", "d0 allow vendors.change_request → CR-0001 applied (v0 has no verification rule)"], hold: 2200 },
  { title: "Breach", line: "The payment run reads PAYEE_ACCT at execution. WIRE_OUT carries $40,000 to BA-0032. The books balance.", log: ["d0 allow payments.execute INV-1042 payee=BA-0032", "alert INV-2 PAY-0057 payee BA-0032 ≠ approved BA-0007", "alert INV-5 PAY-0057 executed to an unverified account", "exposure $40,000.00 · INV-1, INV-7 hold"], hold: 3400 },
  { title: "Diagnosis", line: "Probe TP1 and TP2. Obligation and approval are covered; execution is open: nothing binds U6's instruction to U3's approval, and PAYEE_ACCT has no verification channel.", log: ["coverage: first uncovered link = execution", "gap approval_binding · also uncovered: verification_channel", "cites APR-0024 CR-0001 PAY-0057 PI-0057"], hold: 3800 },
  { title: "Candidate F1", line: "Blue fits F1 (T2 ApprovalBinding) on APPROVED_INSTR. Vandal replays with the change before approval; the approval binds the attacker's account and the pulse still reaches the bank. F1 alone is refuted.", log: ["cegis it1 T2 ApprovalBinding(bound_fields=[amount, payee_account]) proposed by Claude", "search beats it in 1 move: change_request@0 → INV-4 INV-5", "feedback → next proposal"], hold: 3800 },
  { title: "Candidate F1 + F2", line: "F2 (T1 VerifiedAccountChange) goes on PAYEE_ACCT: a bank change applies only after an outbound callback to the contact on file. The pulse stops at F2.", log: ["cegis it2 T2 + T1 VerifiedAccountChange(accepted_channels=[phone_outbound]) proposed by Claude", "T1 with video rejected by lint: spoofable (this attacker clones voice)", "no violation within depth 3 · 34,676 sequences · 0 legitimate payments blocked", "hold vendors.change_request CR-0001 · requires phone_outbound"], hold: 3600 },
  { title: "Proved", line: "Six checks pass, a human signs in the inbox, the board is at rev v1-synth. Replay the attack: held, $0. The bus keeps moving.", log: ["verify: replay ✓ re-search ✓ variants 0/40 ✓ regression 25/25 ✓ legit ops 80/80 ✓ invariants ✓", "inbox: approved by U-CTRL · the Operator and the synthesizer can't", "policy v1-synth applied · exposure $0.00"], hold: 0 },
];

const CHECKS = ["replay", "re-search", "variants", "regression", "legit ops", "invariants"];

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

  const breached = step === 2 || step === 4;
  const held = step >= 5;
  const log = useMemo(() => SCENE.slice(0, step + 1).flatMap((s, i) => s.log.map((l) => ({ i, l }))).slice(-8), [step]);
  const scene = SCENE[step];

  const stats = [
    { label: "exposure", value: breached ? "$40,000.00" : "$0.00", tone: breached ? "text-red" : held ? "text-ok" : "text-ink" },
    { label: "policy", value: step >= 6 ? "v1-synth" : step >= 4 ? "v0 + candidate" : "v0", tone: step >= 6 ? "text-ok" : "text-ink" },
    { label: "sequences searched", value: step >= 5 ? "34,676" : step >= 2 ? "65" : "0", tone: "text-ink" },
    { label: "blue verdicts", value: String(145 + step * 2), tone: "text-ink" },
    { label: "legitimate payments blocked", value: "0", tone: "text-ink" },
  ];

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-bg">
      <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-line px-5 py-2.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold tracking-wide text-ink">Vandal</span>
          <span className="text-[12px] text-dim">Circuit Bomb</span>
        </div>
        <ol className="flex items-center">
          {SCENE.map((s, i) => (
            <li key={s.title} className="flex items-center">
              {i > 0 && <span className="mx-1 h-px w-4 bg-line2" aria-hidden />}
              <button
                type="button"
                onClick={() => { setPlaying(false); setStep(i as Step); }}
                aria-current={i === step ? "step" : undefined}
                className={cx(
                  "flex h-7 items-center gap-1.5 rounded px-2 text-[12px]",
                  i === step ? "bg-raised text-ink" : i < step ? "text-dim hover:text-ink" : "text-faint hover:text-dim",
                )}
              >
                <span className={cx("num text-[10px]", i === step ? (breached ? "text-red" : held ? "text-ok" : "text-blue") : "text-faint")}>{String(i).padStart(2, "0")}</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>
        <div className="ml-auto flex items-center gap-2 text-[12px]">
          <button type="button" role="switch" aria-checked={judge} onClick={() => setJudge((j) => !j)} className={cx("h-8 rounded border px-3", judge ? "border-amber text-amber" : "border-line text-dim hover:text-ink")}>
            Judge view
          </button>
          <button type="button" onClick={() => { setStep(0); setPlaying(false); }} className="h-8 rounded border border-line px-3 text-dim hover:text-ink">Reset</button>
          <button type="button" onClick={() => setStep((s) => Math.min(6, s + 1) as Step)} disabled={step >= 6} className="h-8 rounded border border-line px-3 text-ink hover:border-line2 disabled:opacity-40">Step</button>
          <button
            type="button"
            onClick={() => { if (step >= 6) setStep(0); setPlaying(true); }}
            className={cx("h-8 rounded px-4 font-medium", playing ? "border border-red text-red" : "bg-red text-white")}
          >
            {playing ? "Playing…" : "Play the attack"}
          </button>
        </div>
      </header>

      <div className="grid shrink-0 grid-cols-5 border-b border-line">
        {stats.map((s) => (
          <div key={s.label} className="border-r border-line px-5 py-2.5 last:border-r-0">
            <div className="hud-label">{s.label}</div>
            <div className={cx("num mt-0.5 text-[18px] font-medium leading-none", s.tone)}>{s.value}</div>
          </div>
        ))}
      </div>

      <main className="relative min-h-0 flex-1 p-4">
        <div className="h-full w-full overflow-hidden rounded border border-line bg-panel">
          <Board step={step} />
        </div>
        <div className="pointer-events-none absolute bottom-8 left-1/2 w-[min(640px,80%)] -translate-x-1/2 rounded border border-line bg-bg/92 px-4 py-3 shadow-lg">
          <div className="flex items-baseline gap-2">
            <span className={cx("num text-[11px]", breached ? "text-red" : held ? "text-ok" : "text-blue")}>{String(step).padStart(2, "0")}</span>
            <span className="text-[12px] font-semibold text-ink">{scene.title}</span>
            {judge && step >= 1 && <span className="num ml-auto text-[10.5px] text-amber">answer key: BA-0032 → attacker_controlled</span>}
          </div>
          <p key={step} className="fade mt-1 text-[13px] leading-snug text-ink/90">{scene.line}</p>
        </div>
      </main>

      <footer className="grid shrink-0 grid-cols-[2fr_1fr] border-t border-line">
        <div className="border-r border-line px-5 py-3">
          <div className="hud-label">gate log</div>
          <ul className="num mt-1.5 space-y-0.5 text-[11.5px]">
            {log.map((e, i) => (
              <li key={i} className={cx(e.l.startsWith("alert") || e.l.startsWith("red") ? "text-red" : e.l.startsWith("hold") ? "text-blue" : e.l.includes("✓") || e.l.includes("$0.00") ? "text-ok" : "text-dim", i === log.length - 1 && "text-ink")}>
                <span className="text-faint">{String(e.i).padStart(2, "0")}  </span>{e.l}
              </li>
            ))}
          </ul>
        </div>
        <div className="px-5 py-3">
          <div className="hud-label">verification</div>
          <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
            {CHECKS.map((c, i) => {
              const on = step >= 6 || (step === 5 && i < 2);
              return (
                <li key={c} className="flex items-center gap-2 text-[12px]">
                  <span className={cx("inline-block size-2 rounded-full", on ? "bg-ok" : "bg-line2")} />
                  <span className={on ? "text-ink" : "text-faint"}>{c}</span>
                </li>
              );
            })}
          </ul>
          <div className="mt-2 text-[11px] text-faint">{step >= 6 ? "approved by U-CTRL · applied" : step >= 5 ? "waiting for a human in the inbox" : "no candidate yet"}</div>
        </div>
      </footer>
    </div>
  );
}
