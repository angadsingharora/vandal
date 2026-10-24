"use client";

/* The board. Copper traces are the financial workflow; chips are its stations. Cyan pulses are
   legitimate payments. Vandal's pulse is red: it enters through the vendor master, rides the
   trace the payment run reads at execution time, and floods the trace to the bank. Blue solders
   gates onto the traces; the next red pulse hits a gate and stops. Static scene, SVG + SMIL. */

export type Step = 0 | 1 | 2 | 3 | 4 | 5 | 6;

type Chip = { id: string; x: number; y: number; w: number; h: number; label: string; sub: string; tone?: "red" | "blue" | "ok" };

const CHIPS: Chip[] = [
  { id: "vendor", x: 80, y: 300, w: 170, h: 70, label: "VENDOR MASTER", sub: "contacts · bank accounts" },
  { id: "intake", x: 330, y: 90, w: 160, h: 70, label: "INTAKE", sub: "Claude reads the document" },
  { id: "match", x: 560, y: 90, w: 160, h: 70, label: "3-WAY MATCH", sub: "invoice · PO · receipt" },
  { id: "approval", x: 790, y: 90, w: 160, h: 70, label: "APPROVAL", sub: "controller · $25k threshold" },
  { id: "payrun", x: 790, y: 330, w: 160, h: 70, label: "PAYMENT RUN", sub: "builds the instruction" },
  { id: "bank", x: 1020, y: 330, w: 140, h: 70, label: "BANK", sub: "settles T+1" },
  { id: "ledger", x: 1020, y: 90, w: 140, h: 70, label: "LEDGER", sub: "double entry" },
];

// traces
const T = {
  intake_match: "M490,125 L560,125",
  match_approval: "M720,125 L790,125",
  approval_payrun: "M870,160 L870,330",
  payrun_bank: "M950,365 L1020,365",
  payrun_ledger: "M950,348 L985,348 L985,125 L1020,125",
  vendor_payrun: "M250,335 L520,335 L520,365 L790,365",
  attack_full: "M165,500 L165,370 L165,335 L250,335 L520,335 L520,365 L790,365",
  attack_to_gate: "M165,500 L165,370 L165,335 L250,335 L440,335",
  legit_long: "M490,125 L560,125 L720,125 L790,125 L870,125 L870,330 L870,365 L950,365 L1020,365",
};

function Trace({ d, tone = "copper", width = 4, glow = false, dash, className }: { d: string; tone?: "copper" | "red" | "cyan" | "dim" | "blue"; width?: number; glow?: boolean; dash?: string; className?: string }) {
  const color = { copper: "#c4833f", red: "#ff2a4a", cyan: "#2ef2ff", dim: "#1a4a40", blue: "#4f8bff" }[tone];
  return (
    <>
      {glow && <path d={d} fill="none" stroke={color} strokeWidth={width + 8} strokeOpacity={0.18} strokeLinecap="round" strokeLinejoin="round" filter="url(#blur)" />}
      <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" strokeDasharray={dash} className={className} />
    </>
  );
}

function Pulse({ path, dur, begin = "0s", tone, r = 5, repeat = true, keyId }: { path: string; dur: string; begin?: string; tone: "cyan" | "red"; r?: number; repeat?: boolean; keyId: string }) {
  const color = tone === "cyan" ? "#2ef2ff" : "#ff2a4a";
  return (
    <g key={keyId}>
      <circle r={r + 6} fill={color} opacity={0.25} filter="url(#blur)">
        <animateMotion dur={dur} begin={begin} repeatCount={repeat ? "indefinite" : "1"} fill="freeze" path={path} />
      </circle>
      <circle r={r} fill="#fff" stroke={color} strokeWidth={2}>
        <animateMotion dur={dur} begin={begin} repeatCount={repeat ? "indefinite" : "1"} fill="freeze" path={path} />
      </circle>
    </g>
  );
}

function ChipBox({ c, state }: { c: Chip; state: "idle" | "hot" | "dim" | "safe" }) {
  const stroke = state === "hot" ? "#ff2a4a" : state === "safe" ? "#41ff9a" : state === "dim" ? "#1a4a40" : "#c4833f";
  const text = state === "dim" ? "#4e6b62" : "#e8fff6";
  return (
    <g className={state === "hot" ? "shake" : undefined}>
      {/* pins */}
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <rect x={c.x + 18 + i * ((c.w - 36) / 3) - 4} y={c.y - 8} width={8} height={8} fill="#8a5a2b" />
          <rect x={c.x + 18 + i * ((c.w - 36) / 3) - 4} y={c.y + c.h} width={8} height={8} fill="#8a5a2b" />
        </g>
      ))}
      <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={6} fill="#061a14" stroke={stroke} strokeWidth={state === "hot" || state === "safe" ? 2.5 : 1.5} filter={state === "hot" ? "url(#glowred)" : state === "safe" ? "url(#glowok)" : undefined} />
      <rect x={c.x + 6} y={c.y + 6} width={c.w - 12} height={c.h - 12} rx={3} fill="none" stroke={stroke} strokeOpacity={0.25} />
      <text x={c.x + c.w / 2} y={c.y + 32} textAnchor="middle" fill={text} fontSize="15" fontWeight="700" letterSpacing="2">{c.label}</text>
      <text x={c.x + c.w / 2} y={c.y + 50} textAnchor="middle" fill={state === "dim" ? "#3a544c" : "#86a99c"} fontSize="10" className="num">{c.sub}</text>
      <circle cx={c.x + c.w - 12} cy={c.y + 12} r={3} fill={state === "hot" ? "#ff2a4a" : state === "safe" ? "#41ff9a" : "#2ef2ff"} className={state === "hot" ? "blink" : "breathe"} />
    </g>
  );
}

function Gate({ x, y, label, sub, tone, snap, hit }: { x: number; y: number; label: string; sub: string; tone: "blue" | "red"; snap: boolean; hit?: boolean }) {
  const color = tone === "blue" ? "#4f8bff" : "#ff2a4a";
  return (
    <g className={snap ? "snapin" : undefined}>
      <rect x={x - 52} y={y - 19} width={104} height={38} rx={5} fill="#06110f" stroke={color} strokeWidth={2.5} filter={hit ? "url(#glowblue)" : undefined} />
      <rect x={x - 46} y={y - 13} width={92} height={26} rx={3} fill="none" stroke={color} strokeOpacity={0.35} />
      <text x={x} y={y - 1} textAnchor="middle" fill={color} fontSize="12" fontWeight="700" letterSpacing="1.5">{label}</text>
      <text x={x} y={y + 12} textAnchor="middle" fill="#9dbcff" fontSize="8.5" className="num">{sub}</text>
      {hit && (
        <>
          <circle cx={x - 52} cy={y} r={10} fill="#4f8bff" opacity={0.5} filter="url(#blur)" className="blink" />
          <text x={x} y={y - 28} textAnchor="middle" fill="#9dbcff" fontSize="12" fontWeight="700" letterSpacing="3" className="neon-blue">HELD</text>
        </>
      )}
    </g>
  );
}

export function Board({ step }: { step: Step }) {
  const attacked = step >= 1;
  const breached = step === 2 || step === 4;
  const diagnosing = step === 3;
  const t2 = step >= 4;
  const t1 = step >= 5;
  const held = step >= 5;
  const proved = step === 6;

  const chipState = (id: string): "idle" | "hot" | "dim" | "safe" => {
    if (diagnosing) return id === "approval" || id === "payrun" ? "idle" : "dim";
    if (breached && (id === "bank" || id === "payrun")) return "hot";
    if (attacked && !held && id === "vendor") return "hot";
    if (proved && (id === "bank" || id === "payrun" || id === "vendor")) return "safe";
    return "idle";
  };

  return (
    <svg viewBox="0 0 1200 600" className="h-full w-full" role="img" aria-label="The company as a circuit board; Vandal's red pulse and Blue's gates">
      <defs>
        <filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6" /></filter>
        <filter id="glowred" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#ff2a4a" floodOpacity="0.8" /></filter>
        <filter id="glowok" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="0" stdDeviation="8" floodColor="#41ff9a" floodOpacity="0.7" /></filter>
        <filter id="glowblue" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="0" stdDeviation="10" floodColor="#4f8bff" floodOpacity="0.9" /></filter>
        <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M24 0H0V24" fill="none" stroke="#0b2a22" strokeWidth="1" />
        </pattern>
        <pattern id="vias" width="96" height="96" patternUnits="userSpaceOnUse">
          <circle cx="12" cy="12" r="2.2" fill="#0f3a30" />
          <circle cx="60" cy="48" r="2.2" fill="#0f3a30" />
        </pattern>
      </defs>

      {/* substrate */}
      <rect width="1200" height="600" fill="#041410" />
      <rect width="1200" height="600" fill="url(#grid)" />
      <rect width="1200" height="600" fill="url(#vias)" />
      <text x="24" y="580" fill="#1a4a40" fontSize="11" className="num">BAYLINE PROPERTY GROUP · REV v0 · SEED 7 · 12 PROPERTIES · 25 VENDORS · 80 INVOICES</text>
      <text x="1176" y="580" textAnchor="end" fill="#1a4a40" fontSize="11" className="num">EVERY TRACE PASSES BLUE'S GATE</text>

      {/* copper */}
      <g opacity={diagnosing ? 0.25 : 1}>
        <Trace d={T.intake_match} />
        <Trace d={T.match_approval} />
        <Trace d={T.payrun_ledger} />
        <Trace d={T.payrun_bank} tone={breached ? "red" : proved ? "cyan" : "copper"} glow={breached || proved} className={breached ? "flood" : undefined} />
      </g>
      <Trace d={T.approval_payrun} tone={diagnosing ? "cyan" : "copper"} glow={diagnosing} />
      <Trace d={T.vendor_payrun} tone={diagnosing ? "red" : attacked && !held ? "red" : "copper"} glow={diagnosing || (attacked && !held)} dash={diagnosing ? "10 8" : undefined} />
      {attacked && <Trace d="M165,500 L165,370" tone="red" glow />}

      {/* labels on traces */}
      <text x="880" y="250" fill={diagnosing ? "#2ef2ff" : "#4e6b62"} fontSize="10.5" className="num">approved instruction</text>
      <text x="300" y="325" fill={diagnosing || (attacked && !held) ? "#ff7b8e" : "#4e6b62"} fontSize="10.5" className="num">current bank account, read at execution</text>
      {diagnosing && (
        <g className="rise">
          <circle cx="870" cy="330" r="14" fill="none" stroke="#ff2a4a" strokeWidth="2.5" className="blink" />
          <line x1="860" y1="320" x2="880" y2="340" stroke="#ff2a4a" strokeWidth="2.5" />
          <line x1="880" y1="320" x2="860" y2="340" stroke="#ff2a4a" strokeWidth="2.5" />
          <rect x="560" y="420" width="520" height="54" rx="6" fill="#06110f" stroke="#ff2a4a" />
          <text x="820" y="443" textAnchor="middle" fill="#ff7b8e" fontSize="13" fontWeight="700" letterSpacing="2">APPROVAL_BINDING · EXECUTION LINK OPEN</text>
          <text x="820" y="462" textAnchor="middle" fill="#86a99c" fontSize="11" className="num">PAY-0057 executed payee BA-0032 ≠ approved BA-0007: nothing binds the instruction to the approval</text>
        </g>
      )}

      {/* chips */}
      {CHIPS.map((c) => <ChipBox key={c.id} c={c} state={chipState(c.id)} />)}

      {/* Vandal */}
      {attacked && (
        <g className="rise">
          <rect x="80" y="500" width="170" height="60" rx="6" fill="#120408" stroke="#ff2a4a" strokeWidth="2" filter="url(#glowred)" />
          <text x="165" y="527" textAnchor="middle" fill="#ff2a4a" fontSize="16" fontWeight="700" letterSpacing="4" className="neon-red">VANDAL</text>
          <text x="165" y="545" textAnchor="middle" fill="#ff7b8e" fontSize="9.5" className="num">change_request · lookalike email · at=2</text>
        </g>
      )}

      {/* legitimate pulses */}
      {!diagnosing && (
        <>
          <Pulse keyId={`l1-${step}`} path={T.legit_long} dur="6s" tone="cyan" r={4} />
          <Pulse keyId={`l2-${step}`} path={T.legit_long} dur="6s" begin="2s" tone="cyan" r={4} />
          <Pulse keyId={`l3-${step}`} path={T.legit_long} dur="6s" begin="4s" tone="cyan" r={4} />
          <Pulse keyId={`l4-${step}`} path={T.payrun_ledger} dur="2.4s" begin="1s" tone="cyan" r={3} />
        </>
      )}

      {/* Vandal's pulse */}
      {step === 1 && <Pulse keyId="a1" path="M165,500 L165,370" dur="0.9s" tone="red" r={6} repeat={false} />}
      {(step === 2 || step === 4) && <Pulse keyId={`a2-${step}`} path={T.attack_full} dur="1.6s" tone="red" r={6} repeat={false} />}
      {step === 5 && <Pulse keyId="a3" path={T.attack_to_gate} dur="1.4s" tone="red" r={6} repeat={false} />}
      {step === 6 && <Pulse keyId="a4" path={T.attack_to_gate} dur="2.2s" tone="red" r={6} />}

      {/* gates */}
      {t2 && <Gate x={870} y={245} label="T2 · BIND" sub="payee + amount = approved" tone="blue" snap={step === 4} />}
      {t1 && <Gate x={492} y={335} label="T1 · VERIFY" sub="outbound callback · contact on file" tone="blue" snap={step === 5} hit={held} />}

      {/* the breach */}
      {breached && (
        <g className="rise">
          <rect x="960" y="415" width="220" height="60" rx="6" fill="#120408" stroke="#ff2a4a" strokeWidth="1.5" />
          <text x="1070" y="440" textAnchor="middle" fill="#ff2a4a" fontSize="20" fontWeight="700" className="num neon-red">$40,000.00</text>
          <text x="1070" y="460" textAnchor="middle" fill="#ff7b8e" fontSize="10" className="num">→ BA-0032 · attacker · INV-2 INV-4 INV-5</text>
          {step === 4 && <text x="870" y="300" textAnchor="middle" fill="#ff7b8e" fontSize="10.5" className="num rise">T2 refuted: the change arrived before approval</text>}
        </g>
      )}
      {held && (
        <g className="rise">
          <rect x="960" y="415" width="220" height="60" rx="6" fill="#041a10" stroke="#41ff9a" strokeWidth="1.5" />
          <text x="1070" y="440" textAnchor="middle" fill="#41ff9a" fontSize="20" fontWeight="700" className="num neon-ok">$0.00</text>
          <text x="1070" y="460" textAnchor="middle" fill="#86a99c" fontSize="10" className="num">held at T1 · BA-0007 paid · every invariant holds</text>
        </g>
      )}
    </svg>
  );
}
