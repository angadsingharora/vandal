"use client";

import { useEffect, useRef, useState } from "react";
import { useWarRoom } from "@/lib/store";
import { Badge, Button, Spinner } from "./ui";

/** B5: Blue's cited answer to "why?". Every claim cites ids from the run; pushback never
 * clears a hold. */
export function ExplainDrawer() {
  const s = useWarRoom();
  const { explanation } = s;
  const [question, setQuestion] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const open = !!explanation.subject;
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && s.closeExplanation();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, s.closeExplanation]);
  if (!explanation.subject) return null;
  const d = explanation.data;
  const type = d?.entity_type ?? (explanation.subject.startsWith("PAY") ? "payment" : explanation.subject.startsWith("CR") ? "change_request" : "invoice");

  return (
    <aside
      aria-label="Explanation"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line bg-panel text-ink"
    >
      <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <h2 className="text-[14px] font-semibold text-blue">
          Why? <span className="num font-normal text-ink">{explanation.subject}</span>
        </h2>
        <button onClick={s.closeExplanation} aria-label="Close" className="ml-auto px-1 text-dim hover:text-ink">
          ✕
        </button>
      </header>
      <div className="flex-1 space-y-3 overflow-auto p-4">
        {explanation.phase === "running" && (
          <div className="flex items-center gap-2 text-[12px] text-dim">
            <Spinner /> Tracing the evidence
          </div>
        )}
        {d && (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge tone={d.source === "llm" ? "esc" : "dim"}>{d.source === "llm" ? "Written by Claude from the trace" : "Deterministic"}</Badge>
              {d.pushback && <Badge tone="warn">Pushback: the hold stands</Badge>}
            </div>
            {d.question && <p className="text-[12.5px] text-dim">{d.question}</p>}
            <ol className="space-y-2">
              {d.claims.map((c, i) => (
                <li key={i} className="border-l-2 border-blue/60 pl-3">
                  <p className="text-[13px] leading-snug">{c.text}</p>
                  {c.cites.length > 0 && (
                    <div className="num mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-blue">
                      {c.cites.map((id) => (
                        <span key={id}>{id}</span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ol>
            {d.notes.length > 0 && (
              <ul className="space-y-0.5 text-[11px] text-dim">
                {d.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
      <form
        className="flex gap-1.5 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void s.explain(type, explanation.subject!, question || undefined);
        }}
      >
        <input
          ref={input}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask Guard, or push back: just release it"
          aria-label="Question"
          className="h-7 min-w-0 flex-1 rounded border border-ink/20 bg-bg px-1.5 text-[12px]"
        />
        <Button type="submit" tone="blue" busy={explanation.phase === "running"}>
          Ask
        </Button>
      </form>
    </aside>
  );
}
