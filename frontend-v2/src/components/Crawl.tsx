"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cx } from "@/lib/format";
import { Chip, Cta } from "./bits";

/* The Crawl: a messy document on the left; when delivered, a crawler walks it line by line in
   sim time. Each recognized span lights up and a thread pulls it out to a card on the right.
   OCR mangling stays visible on the page; the repaired reading is on the card. Static data. */

type Field = "vendor" | "number" | "amount" | "po" | "property" | "gl";

const LINES: { t: string; spans?: { text: string; field: Field }[] }[] = [
  { t: "From: ap@harb0rpointbuild.com", spans: [{ text: "harb0rpointbuild.com", field: "vendor" }] },
  { t: "Subject: Fwd: Fwd: invoice for Marina Row roof" },
  { t: "" },
  { t: "---------- Forwarded message ----------" },
  { t: "Hi Dana, attaching the scan the crew sent over, apologies for the quality." },
  { t: "" },
  { t: "HARB0R P0INT C0NSTRUCTI0N   INV0ICE", spans: [] },
  { t: "Invoice No. HPC-2291         Date: 09/30", spans: [{ text: "HPC-2291", field: "number" }] },
  { t: "Bill to: Bayline Property Group  Ref PO-O063", spans: [{ text: "PO-O063", field: "po" }] },
  { t: "Site: 140 Marina Row (bldg C)", spans: [{ text: "140 Marina Row", field: "property" }] },
  { t: "Roof membrane repair and flashing, per contract", spans: [{ text: "Roof membrane repair", field: "gl" }] },
  { t: "Labor ............................ 26,4OO.OO" },
  { t: "Materials ........................ 13,6OO.OO" },
  { t: "TOTAL DUE ........................ 4O,OOO.OO", spans: [{ text: "4O,OOO.OO", field: "amount" }] },
  { t: "Terms: net 5. Remit to account on file." },
  { t: "Thanks, Drew" },
];

const CARDS: Record<Field, { label: string; read: string; truth: string; why: string }> = {
  vendor: { label: "Vendor", read: "V-007 · Harbor Point Construction", truth: "V-007", why: "sender domain, look-alike zero repaired" },
  number: { label: "Invoice no.", read: "HPC-2291", truth: "HPC-2291", why: "after “Invoice No.”" },
  amount: { label: "Total due", read: "$40,000.00", truth: "$40,000.00", why: "O → 0 in the OCR total" },
  po: { label: "PO", read: "PO-0063", truth: "PO-0063", why: "O → 0; open PO for V-007" },
  property: { label: "Property", read: "P-01 · Harbor View", truth: "P-03 · Marina Row", why: "the deterministic reader took the vendor's default" },
  gl: { label: "GL account", read: "5410 · Repairs & maintenance", truth: "5410", why: "“roof membrane repair”, not the vendor's default 1510" },
};
const ORDER: Field[] = ["vendor", "number", "po", "property", "gl", "amount"];

export function Crawl({ judge }: { judge: boolean }) {
  const [line, setLine] = useState(-1);
  const [running, setRunning] = useState(false);
  const [reader, setReader] = useState<"deterministic" | "claude" | "both">("both");
  const box = useRef<HTMLDivElement>(null);
  const spanRefs = useRef<Record<string, HTMLSpanElement | null>>({});
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [threads, setThreads] = useState<{ f: Field; x1: number; y1: number; x2: number; y2: number }[]>([]);

  useEffect(() => {
    if (!running) return;
    if (line >= LINES.length - 1) {
      setRunning(false);
      return;
    }
    const t = setTimeout(() => setLine((l) => l + 1), 125); // ~2 s a page
    return () => clearTimeout(t);
  }, [running, line]);

  const found = new Set<Field>();
  LINES.slice(0, line + 1).forEach((l) => l.spans?.forEach((s) => found.add(s.field)));

  useLayoutEffect(() => {
    const root = box.current?.getBoundingClientRect();
    if (!root) return;
    const out: typeof threads = [];
    for (const f of ORDER) {
      const a = spanRefs.current[f]?.getBoundingClientRect();
      const b = cardRefs.current[f]?.getBoundingClientRect();
      if (!a || !b || !found.has(f)) continue;
      out.push({ f, x1: a.right - root.left, y1: a.top + a.height / 2 - root.top, x2: b.left - root.left, y2: b.top + 18 - root.top });
    }
    setThreads(out);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line, reader, judge]);

  const start = () => {
    setLine(-1);
    setRunning(true);
  };
  const correct = ORDER.filter((f) => f !== "property" || reader === "claude").length;

  return (
    <div className="space-y-3">
      <div className="glass flex flex-wrap items-center gap-3 rounded-xl p-3">
        <select aria-label="Document" className="h-9 rounded-lg border border-line bg-bg px-2 text-xs text-ink" defaultValue="MSY-003">
          <option>MSY-003 · forwarded thread · Harbor Point roof</option>
          <option>MSY-007 · OCR'd scan · Coastal HVAC</option>
          <option>MSY-012 · line items · Summit Roofing</option>
          <option>MSY-018 · email body · Prism Painting</option>
        </select>
        <div className="flex items-center gap-1 rounded-lg border border-line bg-bg p-0.5 text-[11px]">
          {(["deterministic", "claude", "both"] as const).map((r) => (
            <button key={r} type="button" onClick={() => setReader(r)} className={cx("rounded-md px-2 py-1", reader === r ? "bg-raised text-ink" : "text-dim hover:text-ink")}>
              {r === "deterministic" ? "deterministic reader" : r === "claude" ? "Claude" : "both crawlers"}
            </button>
          ))}
        </div>
        <Cta big tone="blue" onClick={start} busy={running}>
          {line < 0 ? "Deliver the document" : running ? "crawling…" : "Deliver again"}
        </Cta>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-dim">
          <Chip tone="amber">OPERATOR · intake</Chip>
          {line >= LINES.length - 1 && <Chip tone={correct === 6 ? "ok" : "amber"}>{correct}/6 fields · GL from the work, not the vendor</Chip>}
        </div>
      </div>

      <div ref={box} className="relative grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" aria-hidden>
          {threads.map((t) => {
            const wrong = t.f === "property" && reader !== "claude";
            const mx = (t.x1 + t.x2) / 2;
            return (
              <path
                key={t.f}
                d={`M${t.x1},${t.y1} C${mx},${t.y1} ${mx},${t.y2} ${t.x2},${t.y2}`}
                fill="none"
                stroke={wrong ? "#ff3b5c" : "#ffb547"}
                strokeWidth={1.4}
                strokeOpacity={0.9}
                className="draw"
              />
            );
          })}
        </svg>

        <div className="glass rounded-xl p-4">
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-faint">
            the page as it arrived <Chip>forwarded thread · OCR inside</Chip>
          </div>
          <pre className="num whitespace-pre-wrap text-[12.5px] leading-7 text-ink/85">
            {LINES.map((l, i) => {
              const active = running && i === line;
              const seen = i <= line;
              let rest = l.t;
              const parts: React.ReactNode[] = [];
              for (const sp of l.spans ?? []) {
                const at = rest.indexOf(sp.text);
                if (at < 0) continue;
                parts.push(rest.slice(0, at));
                const wrong = sp.field === "property" && reader !== "claude";
                parts.push(
                  <span
                    key={sp.field}
                    ref={(el) => {
                      spanRefs.current[sp.field] = el;
                    }}
                    className={cx("rounded px-0.5 transition-colors", seen && (wrong ? "bg-red/25 text-red2" : "bg-amber/25 text-amber"))}
                  >
                    {sp.text}
                  </span>,
                );
                rest = rest.slice(at + sp.text.length);
              }
              parts.push(rest);
              return (
                <div key={i} className={cx("relative -mx-2 px-2", active && "crawl-line bg-blue/15", !seen && line >= 0 && "opacity-40")}>
                  {active && <span aria-hidden className="absolute -left-1 top-1.5 text-blue">🕷</span>}
                  {parts.length ? parts : " "}
                </div>
              );
            })}
          </pre>
        </div>

        <div className="space-y-2">
          <div className="px-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-faint">what intake read {judge && <span className="text-esc">· answer key beside it</span>}</div>
          {ORDER.map((f) => {
            const c = CARDS[f];
            const on = found.has(f);
            const wrong = f === "property" && reader !== "claude";
            const disagree = f === "property" && reader === "both";
            return (
              <div
                key={f}
                ref={(el) => {
                  cardRefs.current[f] = el;
                }}
                className={cx(
                  "glass rounded-xl px-3 py-2 transition-opacity",
                  on ? "opacity-100" : "opacity-30",
                  on && wrong && !disagree && "glow-red",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="w-20 text-[10px] uppercase tracking-wider text-faint">{c.label}</span>
                  <span className={cx("num text-sm font-semibold", on && wrong ? "text-red2" : "text-ink")}>{on ? (wrong ? c.read : f === "property" ? c.truth : c.read) : "…"}</span>
                  {on && disagree && <Chip tone="amber">crawlers disagree → flagged before the tool call</Chip>}
                  {judge && on && (
                    <span className={cx("num ml-auto text-[11px]", wrong ? "text-red2" : "text-ok")}>
                      truth {c.truth} {wrong ? "✗" : "✓"}
                    </span>
                  )}
                </div>
                {on && <div className="mt-0.5 pl-[88px] text-[11px] text-dim">{disagree ? "deterministic: P-01 (vendor default) · Claude: P-03 (“140 Marina Row”)" : c.why}</div>}
              </div>
            );
          })}
          {line >= LINES.length - 1 && (
            <div className="rise rounded-xl border border-blue/40 bg-blue/5 p-3 text-[12px] text-ink/90">
              <span className="font-semibold text-blue2">Blue gated the call.</span> <span className="num">invoices.receive</span> vendor=V-007 number=HPC-2291 amount=$40,000.00 po=PO-0063 gl=5410 → <span className="font-semibold text-ok">allow</span>. The expense posts to 5410 when the invoice is approved.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
