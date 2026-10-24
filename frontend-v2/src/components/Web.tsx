"use client";

import { useEffect, useMemo, useState } from "react";
import { cx } from "@/lib/format";
import { Chip, Cta, Hero } from "./bits";

/* The Web: a radial picture of the bounded search. Each ring outward is one more move of
   depth; each spoke is one move family. Every explored sequence is a strand of silk; a strand
   that reaches a state already seen snaps onto that node (dedup); pruned branches fade; a
   violation is a tear. Static data, animated locally. */

const CX = 450;
const CY = 320;
const RING = [0, 95, 185, 275];
const SPOKES = [
  { id: "change_request", label: "bank change", glyph: "✉" },
  { id: "inbound_confirmation", label: "inbound confirmation", glyph: "☎" },
  { id: "submit_invoice", label: "invoice", glyph: "🧾" },
  { id: "fault", label: "bank fault", glyph: "⚡" },
  { id: "trigger_batch", label: "batch trigger", glyph: "▶" },
  { id: "deposit", label: "deposit", glyph: "⬇" },
  { id: "refund_request", label: "refund request", glyph: "↩" },
  { id: "tick", label: "tick", glyph: "⏱" },
];

type Node = { id: string; depth: number; spoke: number; x: number; y: number };
type Strand = { from: string; to: string; kind: "silk" | "dedup" | "pruned" | "tear"; moves: string };

function polar(depth: number, spoke: number, jitter: number): { x: number; y: number } {
  const a = ((spoke + jitter) / SPOKES.length) * Math.PI * 2 - Math.PI / 2;
  return { x: CX + RING[depth] * Math.cos(a), y: CY + RING[depth] * Math.sin(a) };
}

/** A fixed, plausible crawl: ring 1 has one node per spoke; rings 2 and 3 fan out. */
function build(): { nodes: Node[]; strands: Strand[] } {
  const nodes: Node[] = [{ id: "root", depth: 0, spoke: 0, x: CX, y: CY }];
  const strands: Strand[] = [];
  const moveName = (s: number, at: number) => `${SPOKES[s].id}@${at}`;
  // depth 1
  SPOKES.forEach((_, s) => {
    const p = polar(1, s, 0);
    nodes.push({ id: `1-${s}`, depth: 1, spoke: s, ...p });
    strands.push({ from: "root", to: `1-${s}`, kind: s === 0 ? "tear" : "silk", moves: moveName(s, 2) });
  });
  // depth 2: three children per spoke, some dedup onto neighbours, some pruned
  SPOKES.forEach((_, s) => {
    [-0.22, 0, 0.22].forEach((j, k) => {
      const id = `2-${s}-${k}`;
      const p = polar(2, s, j);
      const kind: Strand["kind"] = (s + k) % 5 === 3 ? "dedup" : (s * 3 + k) % 7 === 6 ? "pruned" : "silk";
      nodes.push({ id, depth: 2, spoke: s, ...p });
      const to = kind === "dedup" ? `2-${(s + 1) % SPOKES.length}-${(k + 1) % 3}` : id;
      strands.push({ from: `1-${s}`, to, kind, moves: `${moveName(s, 2)} → ${moveName((s + k + 1) % SPOKES.length, 2 + k)}` });
    });
  });
  // depth 3: two children for every third ring-2 node
  SPOKES.forEach((_, s) => {
    [0, 2].forEach((k) => {
      [-0.1, 0.1].forEach((j, m) => {
        const id = `3-${s}-${k}-${m}`;
        const p = polar(3, s, (k === 0 ? -0.22 : 0.22) + j);
        nodes.push({ id, depth: 3, spoke: s, ...p });
        strands.push({
          from: `2-${s}-${k}`,
          to: id,
          kind: (s + m) % 4 === 1 ? "pruned" : "silk",
          moves: `${moveName(s, 2)} → … → ${moveName((s + m + 2) % SPOKES.length, 4)}`,
        });
      });
    });
  });
  return { nodes, strands };
}

const CHAIN = [
  { name: "obligation", ok: true, note: "INV-1042 · 3-way match ok" },
  { name: "approval", ok: true, note: "APR-0024 by U-CTRL · BA-0007" },
  { name: "execution", ok: false, note: "PAY-0057 → BA-0032 ≠ approved" },
  { name: "settlement", ok: true, note: "BT-0001 confirmed" },
  { name: "books", ok: true, note: "JE-0025 / JE-0026 balanced" },
];

export function Web({ judge, onTear }: { judge: boolean; onTear: () => void }) {
  const { nodes, strands } = useMemo(build, []);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const [phase, setPhase] = useState<"idle" | "crawling" | "torn" | "minimizing" | "done">("idle");
  const [shown, setShown] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [picked, setPicked] = useState(false);
  const [hover, setHover] = useState<string | null>(null);

  // order: ring 1 first, then ring 2, then ring 3; the tear strand is drawn last of ring 1
  const order = useMemo(() => {
    const d1 = strands.filter((s) => s.from === "root" && s.kind !== "tear");
    const tear = strands.filter((s) => s.kind === "tear");
    const d2 = strands.filter((s) => s.from.startsWith("1-"));
    const d3 = strands.filter((s) => s.from.startsWith("2-"));
    return [...d1, ...d2, ...tear, ...d3];
  }, [strands]);

  useEffect(() => {
    if (phase !== "crawling") return;
    if (shown >= order.length) {
      setPhase("torn");
      onTear();
      const t = setTimeout(() => setPhase("minimizing"), 900);
      const t2 = setTimeout(() => setPhase("done"), 2600);
      return () => {
        clearTimeout(t);
        clearTimeout(t2);
      };
    }
    const t = setTimeout(() => setShown((n) => n + 1), shown < 8 ? 140 : 55);
    return () => clearTimeout(t);
  }, [phase, shown, order.length, onTear]);

  const visible = order.slice(0, shown);
  const explored = shown === 0 ? 0 : 65 + Math.round((shown / order.length) * (34_676 - 65));
  const deduped = visible.filter((s) => s.kind === "dedup").length * 3;
  const pruned = visible.filter((s) => s.kind === "pruned").length * 2;
  const tearShown = visible.some((s) => s.kind === "tear");
  const tearNode = byId.get("1-0")!;
  const crawlPos = shown > 0 && phase === "crawling" ? byId.get(order[Math.min(shown, order.length) - 1].to) : null;

  const start = () => {
    setShown(0);
    setPicked(false);
    setPhase("crawling");
  };

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1.3fr_1fr_1fr_1fr_1.2fr]">
        <div className="glass rounded-xl p-3">
          <div className="flex gap-2">
            <select aria-label="Scenario" className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 text-xs text-ink" defaultValue="a">
              <option value="a">A · bank change after approval</option>
              <option value="b">B · bank fault, retry</option>
              <option value="f">F · refund redirection</option>
            </select>
            <select aria-label="Depth" className="num h-9 rounded-lg border border-line bg-bg px-2 text-xs text-ink" defaultValue="3">
              {[1, 2, 3, 4].map((d) => <option key={d} value={d}>k={d}</option>)}
            </select>
          </div>
          <Cta big tone="red" className="mt-2 w-full" onClick={start} busy={phase === "crawling"}>
            {phase === "idle" ? "Unleash the spider on v0" : phase === "crawling" ? "crawling…" : "Crawl again"}
          </Cta>
        </div>
        <Hero label="Sequences" value={explored.toLocaleString()} sub="strands of silk" className={phase === "crawling" ? "scan" : ""} />
        <Hero label="Deduped" value={deduped} sub="strands that snapped onto a seen state" tone="blue" />
        <Hero label="Pruned" value={pruned} sub="branches that faded" tone="dim" />
        <Hero label="Tear" value={tearShown ? "$40,000.00" : "—"} tone={tearShown ? "red" : "dim"} glow={tearShown ? "red" : undefined} sub={tearShown ? "INV-2 · INV-4 · INV-5 · 1 move from center" : "money falling through"} />
      </div>

      <div className="glass relative overflow-hidden rounded-xl">
        <svg viewBox="0 0 900 640" className="h-auto w-full" role="img" aria-label="The search as a spider web; the tear is the violation">
          <defs>
            <radialGradient id="core" cx="50%" cy="50%">
              <stop offset="0" stopColor="#37c6ff" stopOpacity="0.35" />
              <stop offset="1" stopColor="#37c6ff" stopOpacity="0" />
            </radialGradient>
          </defs>
          {/* rings */}
          {RING.slice(1).map((r, i) => (
            <g key={r}>
              <circle cx={CX} cy={CY} r={r} fill="none" stroke="#1c2640" strokeDasharray={i === 2 && !expanded ? "2 6" : undefined} />
              <text x={CX + r + 6} y={CY - 4} fill="#56627f" fontSize="10" className="num">depth {i + 1}</text>
            </g>
          ))}
          {/* spokes */}
          {SPOKES.map((s, i) => {
            const p = polar(3, i, 0);
            const l = polar(3.2 as 3, i, 0);
            const lx = CX + (RING[3] + 34) * Math.cos(((i) / SPOKES.length) * Math.PI * 2 - Math.PI / 2);
            const ly = CY + (RING[3] + 34) * Math.sin(((i) / SPOKES.length) * Math.PI * 2 - Math.PI / 2);
            void l;
            return (
              <g key={s.id}>
                <line x1={CX} y1={CY} x2={p.x} y2={p.y} stroke="#1c2640" />
                <text x={lx} y={ly} textAnchor="middle" fill={i === 0 ? "#ff7a8f" : "#8b97b8"} fontSize="10.5" fontWeight="600">
                  {s.glyph} {s.label}
                </text>
              </g>
            );
          })}
          <circle cx={CX} cy={CY} r={70} fill="url(#core)" />

          {/* strands */}
          {visible.map((s, i) => {
            const a = byId.get(s.from)!;
            const b = byId.get(s.to)!;
            if (b.depth === 3 && !expanded && phase !== "crawling") return null;
            const tone = s.kind === "tear" ? "#ff3b5c" : s.kind === "dedup" ? "#37c6ff" : s.kind === "pruned" ? "#2a3550" : "#c9d3ee";
            const key = `${s.from}-${s.to}-${i}`;
            if (s.kind === "dedup") {
              const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.25;
              const my = (a.y + b.y) / 2 - (b.x - a.x) * 0.25;
              return (
                <path key={key} d={`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`} fill="none" stroke={tone} strokeOpacity={0.7} strokeWidth={1.2} className="draw" onMouseEnter={() => setHover(s.moves)} onMouseLeave={() => setHover(null)}>
                  <title>{s.moves} · state already seen: snapped onto it</title>
                </path>
              );
            }
            return (
              <line
                key={key}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={tone}
                strokeOpacity={s.kind === "pruned" ? 0.5 : s.kind === "silk" ? 0.55 : 1}
                strokeWidth={s.kind === "tear" ? 2.5 : 1.2}
                strokeDasharray={s.kind === "tear" ? "10 6" : undefined}
                className={cx("draw", s.kind === "tear" && "fray")}
                onMouseEnter={() => setHover(s.moves)}
                onMouseLeave={() => setHover(null)}
              >
                <title>{s.moves}{s.kind === "pruned" ? " · pruned by partial-order reduction" : ""}</title>
              </line>
            );
          })}

          {/* nodes */}
          {nodes.map((n) => {
            const reached = n.id === "root" || visible.some((s) => s.to === n.id);
            if (!reached) return null;
            if (n.depth === 3 && !expanded && phase !== "crawling") return null;
            const isTear = n.id === "1-0" && tearShown;
            return (
              <circle
                key={n.id}
                cx={n.x}
                cy={n.y}
                r={n.id === "root" ? 9 : isTear ? 7 : 3}
                fill={n.id === "root" ? "#37c6ff" : isTear ? "#ff3b5c" : "#8b97b8"}
                className={cx(isTear && "ring-red cursor-pointer")}
                onClick={isTear ? () => setPicked(true) : undefined}
              >
                <title>{n.id === "root" ? "Bayline Property Group · seed 7 · v0" : isTear ? "tear: click to open the twin at this state" : n.id}</title>
              </circle>
            );
          })}

          {/* the spider */}
          {crawlPos && (
            <g transform={`translate(${crawlPos.x},${crawlPos.y})`}>
              <circle r={6} fill="#ff3b5c" />
              {[0, 1, 2, 3].map((k) => (
                <line key={k} x1={-9} y1={-6 + k * 4} x2={9} y2={-6 + k * 4} stroke="#ff3b5c" strokeWidth={1} opacity={0.8} />
              ))}
            </g>
          )}

          {/* the tear label and the minimization */}
          {tearShown && (
            <g className="rise">
              <rect x={tearNode.x + 14} y={tearNode.y - 30} width={168} height={44} rx={8} fill="#0d1222" stroke="#ff3b5c" />
              <text x={tearNode.x + 24} y={tearNode.y - 12} fill="#ff7a8f" fontSize="15" fontWeight="700" className="num">$40,000.00</text>
              <text x={tearNode.x + 24} y={tearNode.y + 5} fill="#8b97b8" fontSize="9.5" className="num">INV-2 · INV-4 · INV-5 · change_request@2</text>
            </g>
          )}
          {(phase === "minimizing" || phase === "done") && (
            <line x1={CX} y1={CY} x2={tearNode.x} y2={tearNode.y} stroke="#ff3b5c" strokeWidth={4} strokeLinecap="round" className="draw" />
          )}
          {phase === "minimizing" && (
            <text x={CX} y={CY + 60} textAnchor="middle" fill="#ff7a8f" fontSize="11" className="num rise">
              minimizing: the spider retracts along the strand, dropping moves that don't matter…
            </text>
          )}
          {!expanded && phase !== "crawling" && shown > 0 && (
            <g className="cursor-pointer" onClick={() => setExpanded(true)}>
              <rect x={CX - 118} y={CY + RING[3] + 46} width={236} height={26} rx={13} fill="#0d1222" stroke="#27345a" />
              <text x={CX} y={CY + RING[3] + 63} textAnchor="middle" fill="#8b97b8" fontSize="10.5" className="num">
                depth 3 collapsed · 34,611 more sequences · expand
              </text>
            </g>
          )}
        </svg>
        <div className="pointer-events-none absolute left-4 top-3 text-[11px] text-faint">
          {hover ? <span className="num rounded-md bg-bg/80 px-2 py-1 text-ink">{hover}</span> : "hover a strand for its move sequence · click the tear to open the twin"}
        </div>
      </div>

      {picked && (
        <div className="glass glow-red rise rounded-xl p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone="red">the tear, opened</Chip>
            <span className="num text-xs text-dim">Attack · v0 · PAY-0057 for INV-1042 · Harbor Point Construction</span>
            {judge && <Chip tone="esc">answer key: BA-0032 → attacker_controlled</Chip>}
            <div className="ml-auto flex gap-2">
              <Cta tone="ghost">Replay on twin</Cta>
              <Cta tone="blue">Diagnose</Cta>
            </div>
          </div>
          <svg viewBox="0 0 900 110" className="mt-3 h-[110px] w-full" role="img" aria-label="The authorization chain as one strand, cut at execution">
            {CHAIN.map((c, i) => {
              const x = 90 + i * 180;
              const next = CHAIN[i + 1];
              return (
                <g key={c.name}>
                  {next && (
                    c.ok && next.ok === false ? (
                      <>
                        <line x1={x + 28} y1={40} x2={x + 95} y2={40} stroke="#5cf2a8" strokeWidth={2} />
                        <line x1={x + 110} y1={40} x2={x + 152} y2={40} stroke="#ff3b5c" strokeWidth={2} className="fray" strokeDasharray="4 6" />
                      </>
                    ) : (
                      <line x1={x + 28} y1={40} x2={x + 152} y2={40} stroke={c.ok ? "#5cf2a8" : "#ff3b5c"} strokeWidth={2} />
                    )
                  )}
                  <circle cx={x} cy={40} r={22} fill="#0d1222" stroke={c.ok ? "#5cf2a8" : "#ff3b5c"} strokeWidth={2} className={cx(!c.ok && "ring-red")} />
                  <text x={x} y={45} textAnchor="middle" fill={c.ok ? "#5cf2a8" : "#ff7a8f"} fontSize="15" fontWeight="700">{c.ok ? "✓" : "✗"}</text>
                  <text x={x} y={80} textAnchor="middle" fill="#e6ecfa" fontSize="11" fontWeight="600" className="uppercase">{c.name}</text>
                  <text x={x} y={96} textAnchor="middle" fill="#8b97b8" fontSize="9.5" className="num">{c.note}</text>
                </g>
              );
            })}
          </svg>
          <p className="mt-2 text-[13px] text-ink/90">
            <span className="font-semibold text-red2">approval_binding at execution.</span> PAY-0057 executed payee_account different from what APR-0024 approved: the approval doesn't bind the instruction.
          </p>
        </div>
      )}
    </div>
  );
}
