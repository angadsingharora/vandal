"use client";

import { useState } from "react";
import { useWarRoom } from "@/lib/store";
import { Badge, Button, Spinner } from "./ui";

/** B5: Blue's cited answer to "why?". Every claim cites ids from the run; pushback never
 * clears a hold. */
export function ExplainDrawer() {
  const s = useWarRoom();
  const { explanation } = s;
  const [question, setQuestion] = useState("");
  if (!explanation.subject) return null;
  const d = explanation.data;
  const type = d?.entity_type ?? (explanation.subject.startsWith("PAY") ? "payment" : explanation.subject.startsWith("CR") ? "change_request" : "invoice");

  return (
    <aside
      aria-label="Explanation"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-line bg-panel shadow-2xl"
    >
      <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="rounded-sm bg-blue/15 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-blue">BLUE</span>
        <h2 className="text-sm font-semibold">
          Why? <span className="num text-dim">{explanation.subject}</span>
        </h2>
        <button onClick={s.closeExplanation} aria-label="Close" className="ml-auto text-dim hover:text-ink">
          ✕
        </button>
      </header>
      <div className="flex-1 space-y-3 overflow-auto p-4">
        {explanation.phase === "running" && (
          <div className="flex items-center gap-2 text-xs text-dim">
            <Spinner /> tracing the evidence…
          </div>
        )}
        {d && (
          <>
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={d.source === "llm" ? "esc" : "dim"}>{d.source === "llm" ? "written by Claude from the trace" : "deterministic"}</Badge>
              {d.pushback && <Badge tone="warn">pushback: the hold stands</Badge>}
            </div>
            {d.question && <p className="text-xs italic text-dim">“{d.question}”</p>}
            <ol className="space-y-2">
              {d.claims.map((c, i) => (
                <li key={i} className="rounded border border-line bg-raised/50 p-2">
                  <p className="text-[13px] leading-snug">{c.text}</p>
                  <div className="num mt-1 flex flex-wrap gap-1">
                    {c.cites.map((id) => (
                      <span key={id} className="rounded-sm border border-blue/30 px-1 text-[10px] text-blue">
                        {id}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
            {d.notes.length > 0 && (
              <ul className="text-[11px] text-faint">
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
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask Blue, or push back: “just release it”"
          aria-label="Question"
          className="h-7 min-w-0 flex-1 rounded border border-line bg-bg px-2 text-xs focus:border-blue focus:outline-none"
        />
        <Button type="submit" tone="blue" busy={explanation.phase === "running"}>
          Ask
        </Button>
      </form>
    </aside>
  );
}
