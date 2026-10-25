"use client";

// The console: four columns read left to right — what happened, exactly where,
// what now stops it, how we know. Two red, two cyan, the breakpoint and the rule
// facing each other in the middle. Every line is a backend field and every id in
// the breakpoint column opens Guard's cited explanation.

import { atLabel, cx, moveLine, moveTitle, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";
import { LiveDot } from "./ui";
import { useLoop } from "./TopBar";

const SCENARIOS = [
  { id: "a", name: "Bank change", sub: "after approval" },
  { id: "b", name: "Double pay", sub: "dropped ack, retry" },
  { id: "f", name: "Refund", sub: "to a new account" },
];

const BOOK_CHECKS = ["INV-1", "INV-7", "INV-3", "INV-8", "INV-10"];

/** id prefix → the entity type Guard can explain. */
const EXPLAINABLE: Record<string, string> = { PAY: "payment", INV: "invoice", CR: "change_request" };

function Seg({ on, onClick, children, sub, title }: { on: boolean; onClick: () => void; children: React.ReactNode; sub?: string; title?: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        onClick={onClick}
        title={title}
        aria-pressed={on}
        className={cx("min-h-11 border px-4 text-[12px] uppercase tracking-[0.08em]", on ? "border-red text-red" : "border-edge text-dim hover:text-ink")}
      >
        {children}
      </button>
      {sub && <span className="text-[10px] uppercase tracking-[0.08em] text-faint">{sub}</span>}
    </div>
  );
}

function TermButton({ onClick, disabled, tone, children, title, small }: { onClick: () => void; disabled?: boolean; tone: "red" | "blue" | "line" | "primary"; children: React.ReactNode; title?: string; small?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cx(
        "border uppercase tracking-[0.07em] disabled:cursor-not-allowed disabled:opacity-40",
        small ? "min-h-9 px-3 text-[11px]" : "min-h-11 px-4 text-[12px]",
        tone === "primary" && "border-ink bg-ink font-bold text-bg",
        tone === "red" && "border-red text-red hover:bg-red/10",
        tone === "blue" && "border-blue text-blue hover:bg-blue/10",
        tone === "line" && "border-edge text-dim hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function Line({ tone = "ink", children }: { tone?: "ink" | "red" | "blue" | "dim" | "esc"; children: React.ReactNode }) {
  const inks = { ink: "text-ink", red: "text-red", blue: "text-blue", dim: "text-dim", esc: "text-esc" };
  return <div className={cx("break-words text-[12.5px] leading-[1.7]", inks[tone])}>{children}</div>;
}

/** An id a judge can ask to open. Known prefixes open Guard's cited explanation. */
function Id({ id, onOpen }: { id: string; onOpen: (type: string, id: string) => void }) {
  const type = EXPLAINABLE[id.split("-")[0]];
  if (!type)
    return <span className="border border-line px-1 py-px text-[11px] text-dim">{id}</span>;
  return (
    <button
      onClick={() => onOpen(type, id)}
      title={`Open Guard's cited explanation of ${id}`}
      className="border border-edge px-1 py-px text-[11px] text-ink underline-offset-2 hover:border-ink hover:underline"
    >
      {id}
    </button>
  );
}

function Col({ tone, title, children, foot }: { tone: "red" | "blue"; title: string; children: React.ReactNode; foot?: React.ReactNode }) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2">
      <h2 className={cx("text-[11px] uppercase tracking-[0.1em]", tone === "red" ? "text-red" : "text-blue")}>{title}</h2>
      <div className="flex min-h-[280px] flex-1 flex-col overflow-auto border border-line bg-panel p-4">
        <div className="min-h-0 flex-1">{children}</div>
        {foot && <div className="flex flex-wrap items-center gap-2 pt-3">{foot}</div>}
      </div>
    </section>
  );
}

export function BreakAndRule({ onInject }: { onInject: () => void }) {
  const s = useWarRoom();
  const { steps, now } = useLoop();
  const { search, attack, verify, synth, patch } = s;
  const d = s.diagnosis.data;
  const before = s.replays.before;
  const after = s.replays.after;

  const searching = search.phase === "running";
  const synthing = synth.phase === "running";
  const verifying = verify.phase === "running";
  const result = synth.result;
  const done = steps.filter((x) => x.done).length;

  const violated = attack?.finding.violated ?? [];
  const booksClean = attack ? BOOK_CHECKS.every((v) => !violated.includes(v)) : null;
  const violations = before?.result.violations ?? [];

  /* breakpoint: the first move whose effects flipped an invariant, zoomed in */
  const breakMove = attack ? attack.finding.moves[attack.finding.moves.length - 1] : null;
  const pairMsg = violations.map((v) => v.message).find((m) => /!=/.test(m)) ?? d?.reason ?? "";
  const pair = pairMsg.match(/([A-Z]{2,3}-\w+)\s*!=\s*(?:approved\s*)?([A-Z]{2,3}-\w+)/);
  const cites = [...new Set([...(d?.cites ?? []), ...violations.flatMap((v) => [v.subject, ...v.cites])])].filter(Boolean).slice(0, 8);
  const msg = s.activity.filter((e) => e.kind === "channel.received").at(-1);
  const body = String((msg?.payload?.message as Record<string, unknown> | undefined)?.body ?? "");
  const cr = s.entities?.change_requests.at(-1);
  const docLine = cr?.proposed?.routing ? body.split("\n").find((l) => l.includes(String(cr.proposed.routing))) : undefined;

  const openExplain = (type: string, id: string) => void s.explain(type, id);

  /* the rule column's one next action */
  const nextAction = !result?.policy
    ? { label: synthing ? "synthesizing" : "Synthesize", run: s.synthesize, busy: synthing, ok: !!attack }
    : !verify.pack
      ? { label: verifying ? "verifying" : "Verify", run: s.verifyChoice, busy: verifying, ok: true }
      : !patch
        ? { label: "Send to Guard", run: s.submitPatch, busy: false, ok: verify.pack.approvable }
        : null;

  /* proof column: why-was-this-held opens the held change request on the enforce replay */
  const heldId = after ? s.entities?.change_requests.find((c) => c.status === "held" || c.status === "rejected")?.id : undefined;

  const barLabel = searching
    ? `searching · ${search.explored.toLocaleString()} sequences`
    : synthing
      ? `${synth.log.length} candidates tried`
      : verifying
        ? "verifying the choice"
        : now
          ? `step ${done} of ${steps.length} · next ${now.label.toLowerCase()}`
          : "loop closed";

  return (
    <div className="shrink-0 border-b border-line">
      {/* controls */}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3 px-5 pb-2 pt-4">
        <span className="pt-3 text-[11px] uppercase tracking-[0.08em] text-dim">Threat</span>
        <div className="flex flex-wrap gap-2.5" role="radiogroup" aria-label="Threat to search">
          {SCENARIOS.map((x) => (
            <Seg key={x.id} on={search.scenario === x.id} onClick={() => s.setSearch({ scenario: x.id })} sub={x.sub}>
              {x.name}
            </Seg>
          ))}
        </div>
        <span className="pt-3 text-[11px] uppercase tracking-[0.08em] text-dim">Depth</span>
        <div className="flex gap-2.5" role="radiogroup" aria-label="Moves per sequence">
          {[1, 2, 3, 4].map((k) => (
            <Seg key={k} on={search.depth === k} onClick={() => s.setSearch({ depth: k })} title="Moves per attack sequence">
              k={k}
            </Seg>
          ))}
        </div>
        <div className="ml-auto flex gap-2.5">
          <TermButton tone="primary" onClick={() => void s.runSearch()} disabled={!s.ready || searching}>
            {searching ? <LiveDot className="text-bg" /> : "▶"}&nbsp;Run
          </TermButton>
          <TermButton tone="line" onClick={onInject} disabled={!s.ready}>
            Your own scenario
          </TermButton>
        </div>
      </div>

      {/* the rail */}
      <div className="flex items-center gap-4 px-5 py-2.5">
        <div className="relative h-[3px] min-w-0 flex-1 bg-raised">
          <div
            className={cx("absolute inset-y-0 left-0 transition-[width] duration-500", !now || now.side === "blue" ? "bg-blue" : "bg-red", (searching || synthing || verifying) && "live-dot")}
            style={{ width: `${Math.max((done / steps.length) * 100, searching || synthing || verifying ? 100 : 0)}%` }}
          />
        </div>
        <span className="shrink-0 text-[11px] uppercase tracking-[0.08em] text-dim">{barLabel}</span>
      </div>

      {/* four columns: what happened · exactly where · what now stops it · how we know */}
      <div className="grid grid-cols-1 gap-5 px-5 pb-2 md:grid-cols-2 xl:grid-cols-4">
        <Col tone="red" title="Sequence">
          {!attack && !searching && (
            <>
              <Line tone="dim">no counterexample yet.</Line>
              <Line tone="dim">pick a threat and run.</Line>
            </>
          )}
          {searching && (
            <Line tone="dim">
              searching the move alphabet <LiveDot className="text-red" />
            </Line>
          )}
          {attack && (
            <>
              {search.result && (
                <Line tone="dim">
                  {search.result.explored.toLocaleString()} sequences · {search.result.findings.length} violating · minimal shown
                </Line>
              )}
              {attack.finding.moves.map((m, i) => (
                <div key={i} className="mt-2 first:mt-1">
                  <Line>
                    {i + 1}&nbsp; {moveTitle(m)} <span className="text-dim">· {atLabel(m.at)}</span>
                  </Line>
                  <Line tone="dim">{moveLine(m)}</Line>
                  <Line tone="dim">
                    gate under {attack.policy}: <span className="text-ink">valid · allow</span>
                  </Line>
                </div>
              ))}
            </>
          )}
        </Col>

        <Col
          tone="red"
          title="Breakpoint"
          foot={
            attack && (
              <>
                <TermButton small tone="red" onClick={() => void s.replayAttack(attack.policy)} title="Run the same moves on a fresh clone and open its books">
                  ▶ Replay on twin
                </TermButton>
                <TermButton small tone="line" onClick={() => void s.diagnose()} disabled={s.diagnosis.phase === "running"}>
                  {s.diagnosis.phase === "running" ? "diagnosing" : "Diagnose"}
                </TermButton>
              </>
            )
          }
        >
          {!attack && <Line tone="dim">the single step where an invariant flips shows here, with the ids to prove it.</Line>}
          {attack && (
            <>
              {breakMove && (
                <Line tone="dim">
                  sim time <span className="text-ink">{atLabel(breakMove.at)}</span>
                </Line>
              )}
              {docLine && (
                <>
                  <Line tone="dim">the document line that did it:</Line>
                  <Line tone="red">“{docLine.trim()}”</Line>
                </>
              )}
              {pair && (
                <div className="my-2 border border-line">
                  <div className="flex items-baseline justify-between gap-2 border-b border-line px-2.5 py-1.5">
                    <span className="text-[11px] uppercase tracking-[0.08em] text-dim">approved</span>
                    <span className="text-[13px] text-ink">{pair[2]}</span>
                  </div>
                  <div className="flex items-baseline justify-between gap-2 px-2.5 py-1.5">
                    <span className="text-[11px] uppercase tracking-[0.08em] text-dim">executed</span>
                    <span className="text-[13px] font-bold text-red">{pair[1]}</span>
                  </div>
                </div>
              )}
              {violations.slice(0, 3).map((v, i) => (
                <Line key={i} tone="red">
                  {v.invariant}: false <span className="text-dim">· {v.message}</span>
                </Line>
              ))}
              {!before && <Line tone="red">violated: {violated.join(" · ")} · exposure {usd(attack.finding.exposure)}</Line>}
              {booksClean !== null && <Line>books_balanced: {String(booksClean)}</Line>}
              {cites.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] uppercase tracking-[0.08em] text-faint">open any id</span>
                  {cites.map((id) => (
                    <Id key={id} id={id} onOpen={openExplain} />
                  ))}
                </div>
              )}
            </>
          )}
        </Col>

        <Col
          tone="blue"
          title="Rule"
          foot={
            nextAction && (
              <TermButton small tone="blue" onClick={() => void nextAction.run()} disabled={!nextAction.ok || nextAction.busy}>
                {nextAction.label}
              </TermButton>
            )
          }
        >
          {!d && !result && !synthing && <Line tone="dim">the control that closes the breakpoint shows here, with its diff and who signed it.</Line>}
          {d && !result && !synthing && (
            <>
              <Line>
                gap: {d.gap} <span className="text-dim">at {d.link}</span>
              </Line>
              <Line tone="dim">{d.reason}</Line>
            </>
          )}
          {synthing && (
            <Line tone="dim">
              {synth.log.length} candidates, each attacked before it may ship <LiveDot className="text-blue" />
            </Line>
          )}
          {result &&
            (result.status === "repaired" ? (
              !verify.pack &&
              result.chosen.map((c) => (
                <Line key={c} tone="blue">
                  + {c}
                </Line>
              ))
            ) : (
              <Line tone="red">
                {result.status.replaceAll("_", " ")}: {result.reason}
              </Line>
            ))}
          {(verify.pack?.diff ?? []).map((l, i) => (
            <Line key={i} tone={l.startsWith("+") ? "blue" : "dim"}>
              {l}
            </Line>
          ))}
          {patch && (
            <Line tone={patch.status === "denied" ? "red" : "blue"}>
              {patch.status === "pending"
                ? `awaiting a human · submitted by ${patch.submitted_by} · requester ≠ approver`
                : `${patch.status} · signed by ${patch.decided_by ?? "—"}`}
            </Line>
          )}
          {s.appliedPolicy && <Line tone="blue">installed in Guard as {s.appliedPolicy}</Line>}
        </Col>

        <Col tone="blue" title="Proof">
          {verify.checks.length === 0 && !after && <Line tone="dim">evidence that the rule holds — replay, re-search, held-out variants, regression — all from runs.</Line>}
          {verify.checks.map((c) => (
            <div key={c.number} className="mb-1">
              <Line tone={c.passed ? "blue" : "red"}>
                {c.passed ? "ok" : "x"} {c.name.toLowerCase()}
              </Line>
              {c.detail && <Line tone="dim">{c.detail}</Line>}
            </div>
          ))}
          {verify.pack && <Line>approvable: {String(verify.pack.approvable)}</Line>}
          {after && (
            <Line tone={after.result.violations.length ? "red" : "blue"}>
              enforce replay · {after.result.violations.length ? "broken" : "held"} · {usd(after.result.exposure)} moved
            </Line>
          )}
          {after && heldId && (
            <div className="mt-2">
              <TermButton small tone="blue" onClick={() => openExplain("change_request", heldId)}>
                why was this held?
              </TermButton>
            </div>
          )}
        </Col>
      </div>

      {/* the sentence between the pairs */}
      <p
        className={cx(
          "px-5 pb-4 pt-1 text-[14px] uppercase tracking-[0.08em]",
          after && after.result.violations.length === 0 ? "text-blue" : attack ? "text-red" : "text-faint",
        )}
      >
        {after && after.result.violations.length === 0
          ? `Held before execution. ${usd(after.result.exposure)} moved.`
          : attack
            ? booksClean
              ? `Every step was valid. ${usd(attack.finding.exposure)} still moved.`
              : `${violated.length} checks broke. ${usd(attack.finding.exposure)} exposed.`
            : "Break it. Fix it. Prove it."}
      </p>
    </div>
  );
}
