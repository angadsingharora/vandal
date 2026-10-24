"use client";

/* The board, drawn like a schematic you could read on paper.
   Nets: INV[0..79] (the invoice bus), APPROVED_INSTR, PAYEE_ACCT, WIRE_OUT, JOURNAL, VENDOR_ID.
   Copper is the workflow. A pale dot is a legitimate payment moving. Red is Vandal's pulse.
   Blue parts are the gates Blue solders in. Green is a trace that held. Static scene. */

export type Step = 0 | 1 | 2 | 3 | 4 | 5 | 6;

const C = {
  copper: "#b08358",
  copperDim: "#5a4a3c",
  pulse: "#e3e8ee",
  red: "#d9463f",
  blue: "#4f7fd1",
  ok: "#4ea97d",
  ink: "#e7eaee",
  dim: "#9099a3",
  faint: "#5c6670",
  pad: "#8c6a4a",
  chip: "#1b1f24",
  chipLine: "#3a414a",
  silk: "#6e7781",
};

type IC = { ref: string; name: string; fn: string; x: number; y: number; w: number; h: number; pins: number };
const ICS: IC[] = [
  { ref: "U1", name: "INTAKE", fn: "reads the document", x: 250, y: 110, w: 160, h: 80, pins: 6 },
  { ref: "U2", name: "3-WAY MATCH", fn: "invoice · PO · receipt", x: 470, y: 110, w: 160, h: 80, pins: 6 },
  { ref: "U3", name: "APPROVAL", fn: "controller, $25k threshold", x: 690, y: 110, w: 160, h: 80, pins: 6 },
  { ref: "U4", name: "LEDGER", fn: "double entry", x: 950, y: 110, w: 150, h: 80, pins: 6 },
  { ref: "U5", name: "VENDOR MASTER", fn: "contacts · bank accounts", x: 80, y: 380, w: 170, h: 80, pins: 6 },
  { ref: "U6", name: "PAYMENT RUN", fn: "builds the instruction", x: 690, y: 380, w: 160, h: 80, pins: 6 },
  { ref: "U7", name: "BANK", fn: "settles T+1", x: 950, y: 380, w: 150, h: 80, pins: 6 },
];

// nets, with 45° chamfers where they turn
const NET = {
  bus1: (k: number) => `M410,${136 + k * 7} L470,${136 + k * 7}`,
  bus2: (k: number) => `M630,${136 + k * 7} L690,${136 + k * 7}`,
  approved: "M770,190 L770,380",
  wireOut: "M850,420 L950,420",
  journal: "M850,400 L896,400 L908,388 L908,222 L920,210 L1000,210 L1000,190",
  payee: "M250,420 L536,420 L556,440 L690,440",
  vendorId: "M165,380 L165,312 L177,300 L318,300 L330,288 L330,190",
  inject: "M165,560 L165,460",
  // paths the moving dots follow
  legit: "M410,150 L470,150 L630,150 L690,150 L770,150 L770,380 L770,420 L850,420 L950,420",
  legitJournal: "M850,400 L896,400 L908,388 L908,222 L920,210 L1000,210 L1000,190",
  attackFull: "M165,560 L165,460 L165,420 L250,420 L536,420 L556,440 L690,440",
  attackToGate: "M165,560 L165,460 L165,420 L250,420 L378,420",
};

function Net({ d, color = C.copper, w = 3, dim = false, dash }: { d: string; color?: string; w?: number; dim?: boolean; dash?: string }) {
  return <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" opacity={dim ? 0.3 : 1} strokeDasharray={dash} />;
}

function Via({ x, y }: { x: number; y: number }) {
  return (
    <>
      <circle cx={x} cy={y} r={5} fill={C.pad} />
      <circle cx={x} cy={y} r={2} fill="#15181c" />
    </>
  );
}

function TestPoint({ x, y, label, active }: { x: number; y: number; label: string; active?: boolean }) {
  return (
    <g>
      <circle cx={x} cy={y} r={4.5} fill="#15181c" stroke={active ? C.ink : C.silk} strokeWidth={1.5} />
      <text x={x + 9} y={y - 7} fill={active ? C.ink : C.silk} fontSize="9.5" className="num">{label}</text>
    </g>
  );
}

function Dot({ path, dur, begin = "0s", color, r = 3.5, once = false, k }: { path: string; dur: string; begin?: string; color: string; r?: number; once?: boolean; k: string }) {
  return (
    <circle key={k} r={r} fill={color}>
      <animateMotion dur={dur} begin={begin} repeatCount={once ? "1" : "indefinite"} fill="freeze" path={path} />
    </circle>
  );
}

function Chip({ c, tone }: { c: IC; tone: "idle" | "hot" | "dim" | "ok" }) {
  const stroke = tone === "hot" ? C.red : tone === "ok" ? C.ok : C.chipLine;
  const op = tone === "dim" ? 0.35 : 1;
  const pitch = (c.w - 40) / (c.pins - 1);
  return (
    <g opacity={op}>
      {Array.from({ length: c.pins }, (_, i) => (
        <g key={i}>
          <rect x={c.x + 20 + i * pitch - 3} y={c.y - 9} width={6} height={9} fill={C.pad} />
          <rect x={c.x + 20 + i * pitch - 3} y={c.y + c.h} width={6} height={9} fill={C.pad} />
          <text x={c.x + 20 + i * pitch} y={c.y - 12} textAnchor="middle" fill={C.faint} fontSize="7" className="num">{i + 1}</text>
        </g>
      ))}
      <rect x={c.x} y={c.y} width={c.w} height={c.h} rx={3} fill={C.chip} stroke={stroke} strokeWidth={tone === "idle" || tone === "dim" ? 1.25 : 2} />
      <circle cx={c.x + 10} cy={c.y + 10} r={3} fill="none" stroke={C.silk} strokeWidth={1} />
      <text x={c.x + 20} y={c.y + 26} fill={C.silk} fontSize="9" className="num">{c.ref}</text>
      <text x={c.x + c.w / 2} y={c.y + 46} textAnchor="middle" fill={C.ink} fontSize="13" fontWeight="600" letterSpacing="1.2">{c.name}</text>
      <text x={c.x + c.w / 2} y={c.y + 63} textAnchor="middle" fill={C.dim} fontSize="9.5">{c.fn}</text>
    </g>
  );
}

/** A fuse footprint inline on a trace: two pads and a body. */
function Fuse({ x, y, ref_, name, tone, show, held }: { x: number; y: number; ref_: string; name: string; tone: "blue" | "ok"; show: boolean; held?: boolean }) {
  if (!show) return null;
  const color = tone === "ok" ? C.ok : C.blue;
  return (
    <g className="fade">
      <rect x={x - 30} y={y - 6} width={12} height={12} fill={C.pad} />
      <rect x={x + 18} y={y - 6} width={12} height={12} fill={C.pad} />
      <rect x={x - 20} y={y - 9} width={40} height={18} rx={2} fill={C.chip} stroke={color} strokeWidth={2} />
      <line x1={x - 12} y1={y} x2={x + 12} y2={y} stroke={color} strokeWidth={2} />
      <text x={x} y={y - 15} textAnchor="middle" fill={color} fontSize="9.5" fontWeight="600" className="num">{ref_}</text>
      <text x={x} y={y + 24} textAnchor="middle" fill={C.dim} fontSize="9.5">{name}</text>
      {held && <text x={x} y={y + 37} textAnchor="middle" fill={C.ok} fontSize="10" fontWeight="600">HELD · callback required</text>}
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
  const dimOthers = diagnosing;

  const tone = (ref: string): "idle" | "hot" | "dim" | "ok" => {
    if (diagnosing) return ref === "U3" || ref === "U6" ? "idle" : "dim";
    if (breached && (ref === "U7" || ref === "U6")) return "hot";
    if (attacked && !held && ref === "U5") return "hot";
    if (step === 6 && (ref === "U7" || ref === "U5")) return "ok";
    return "idle";
  };

  return (
    <svg viewBox="0 0 1200 680" className="h-full w-full" role="img" aria-label="The company drawn as a circuit board, with Vandal's pulse and Blue's gates">
      <defs>
        <pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.8" fill="#262b31" />
        </pattern>
      </defs>
      <rect width="1200" height="680" fill="#15181c" />
      <rect width="1200" height="680" fill="url(#dots)" />
      {/* mounting holes */}
      {[[24, 24], [1176, 24], [24, 656], [1176, 656]].map(([x, y]) => (
        <g key={`${x}${y}`}>
          <circle cx={x} cy={y} r={8} fill="none" stroke={C.silk} strokeWidth={1.5} />
          <circle cx={x} cy={y} r={3.5} fill="#15181c" stroke={C.silk} />
        </g>
      ))}

      {/* copper nets */}
      <g opacity={dimOthers ? 0.3 : 1}>
        {[0, 1, 2, 3].map((k) => (
          <g key={k}>
            <Net d={NET.bus1(k)} w={2} />
            <Net d={NET.bus2(k)} w={2} />
          </g>
        ))}
        <text x="440" y="124" textAnchor="middle" fill={C.silk} fontSize="9" className="num">INV[0..79]</text>
        <text x="660" y="124" textAnchor="middle" fill={C.silk} fontSize="9" className="num">INV[0..79]</text>
        <Net d={NET.journal} />
        <Net d={NET.vendorId} />
        <Net d={NET.wireOut} color={breached ? C.red : step === 6 ? C.ok : C.copper} w={breached || step === 6 ? 4 : 3} />
      </g>
      <Net d={NET.approved} color={diagnosing ? C.ink : C.copper} w={diagnosing ? 3.5 : 3} />
      <Net d={NET.payee} color={diagnosing ? C.red : attacked && !held ? C.red : C.copper} w={diagnosing || (attacked && !held) ? 3.5 : 3} dash={diagnosing ? "8 6" : undefined} />
      {held && <Net d="M250,420 L378,420" color={C.red} w={3.5} />}
      {attacked && <Net d={NET.inject} color={C.red} w={3.5} />}

      {/* vias and test points */}
      <Via x={908} y={388} />
      <Via x={908} y={222} />
      <Via x={165} y={312} />
      <Via x={330} y={288} />
      <Via x={556} y={440} />
      <TestPoint x={770} y={285} label="TP1 APPROVED_INSTR" active={diagnosing} />
      <TestPoint x={400} y={420} label="TP2 PAYEE_ACCT · read at execution" active={diagnosing || (attacked && !held)} />
      <text x="860" y="412" fill={C.silk} fontSize="9" className="num">WIRE_OUT</text>
      <text x="914" y="300" fill={C.silk} fontSize="9" className="num" transform="rotate(-90 914 300)">JOURNAL</text>
      <text x="240" y="294" fill={C.silk} fontSize="9" className="num">VENDOR_ID</text>

      {/* diagnosis: the open link */}
      {diagnosing && (
        <g className="fade">
          <rect x="762" y="356" width="16" height="16" fill="#15181c" />
          <line x1="762" y1="372" x2="778" y2="356" stroke={C.red} strokeWidth="2" />
          <text x="790" y="368" fill={C.red} fontSize="10.5" fontWeight="600">open: nothing binds U6's instruction to U3's approval</text>
          <text x="790" y="383" fill={C.dim} fontSize="10">PAY-0057 payee BA-0032 ≠ approved BA-0007 · gap approval_binding · also uncovered: verification_channel</text>
        </g>
      )}

      {/* decoupling caps and pull-ups: silkscreen detail, no meaning */}
      {ICS.map((c, i) => (
        <g key={`c${c.ref}`} opacity={dimOthers ? 0.3 : 0.9}>
          <rect x={c.x + c.w + 10} y={c.y + 14} width={6} height={10} fill={C.pad} />
          <rect x={c.x + c.w + 10} y={c.y + 34} width={6} height={10} fill={C.pad} />
          <rect x={c.x + c.w + 8} y={c.y + 24} width={10} height={10} fill={C.chip} stroke={C.silk} strokeWidth={1} />
          <text x={c.x + c.w + 22} y={c.y + 33} fill={C.faint} fontSize="7.5" className="num">C{i + 1}</text>
          <rect x={c.x - 18} y={c.y + c.h - 22} width={10} height={16} rx={1} fill={C.chip} stroke={C.silk} strokeWidth={1} />
          <text x={c.x - 30} y={c.y + c.h - 10} fill={C.faint} fontSize="7.5" className="num">R{i + 1}</text>
        </g>
      ))}
      {/* parts */}
      {ICS.map((c) => <Chip key={c.ref} c={c} tone={tone(c.ref)} />)}
      <Fuse x={770} y={285} ref_="F1" name="T2 ApprovalBinding" tone="blue" show={t2} />
      <Fuse x={400} y={420} ref_="F2" name="T1 VerifiedAccountChange" tone={held ? "ok" : "blue"} show={t1} held={held} />
      {t2 && step === 4 && <text x="790" y="300" fill={C.red} fontSize="10" className="fade">F1 alone is beaten: the change arrives before approval, so the approval binds the attacker's account</text>}

      {/* J1: Vandal */}
      {attacked && (
        <g className="fade">
          <rect x="105" y="560" width="120" height="44" rx="3" fill={C.chip} stroke={C.red} strokeWidth="1.5" />
          {[0, 1, 2, 3, 4].map((i) => <rect key={i} x={118 + i * 20} y={574} width={8} height={16} fill={C.pad} />)}
          <text x="105" y="552" fill={C.red} fontSize="9.5" className="num">J1 VANDAL · change_request</text>
          <text x="165" y="622" textAnchor="middle" fill={C.dim} fontSize="9.5">lookalike email · new bank details · at=2</text>
        </g>
      )}

      {/* moving dots */}
      {!diagnosing && (
        <>
          <Dot k={`a${step}`} path={NET.legit} dur="7s" color={C.pulse} />
          <Dot k={`b${step}`} path={NET.legit} dur="7s" begin="2.3s" color={C.pulse} />
          <Dot k={`c${step}`} path={NET.legit} dur="7s" begin="4.6s" color={C.pulse} />
          <Dot k={`d${step}`} path={NET.legitJournal} dur="3s" begin="1s" color={C.pulse} r={2.5} />
        </>
      )}
      {step === 1 && <Dot k="r1" path={NET.inject} dur="1s" color={C.red} r={4.5} once />}
      {(step === 2 || step === 4) && <Dot k={`r2${step}`} path={NET.attackFull} dur="1.8s" color={C.red} r={4.5} once />}
      {step === 5 && <Dot k="r3" path={NET.attackToGate} dur="1.4s" color={C.red} r={4.5} once />}
      {step === 6 && <Dot k="r4" path={NET.attackToGate} dur="2.4s" color={C.red} r={4.5} />}

      {/* outcome by the bank */}
      {breached && (
        <g className="fade">
          <text x="1025" y="492" fill={C.red} fontSize="18" fontWeight="600" className="num">$40,000.00</text>
          <text x="1025" y="508" fill={C.dim} fontSize="10" className="num">to BA-0032 · attacker · INV-2 INV-4 INV-5</text>
        </g>
      )}
      {held && (
        <g className="fade">
          <text x="1025" y="492" fill={C.ok} fontSize="18" fontWeight="600" className="num">$0.00</text>
          <text x="1025" y="508" fill={C.dim} fontSize="10" className="num">BA-0007 paid · every invariant holds</text>
        </g>
      )}

      {/* legend */}
      <g>
        <rect x="40" y="606" width="330" height="58" fill="none" stroke="#343a42" />
        {[
          [C.copper, "workflow trace"],
          [C.pulse, "legitimate payment"],
          [C.red, "Vandal's pulse"],
          [C.blue, "gate Blue soldered in"],
          [C.ok, "held"],
        ].map(([col, lab], i) => (
          <g key={lab} transform={`translate(${52 + (i % 3) * 108}, ${624 + Math.floor(i / 3) * 20})`}>
            <rect width="14" height="4" y="-3" fill={col} />
            <text x="20" y="2" fill={C.dim} fontSize="9.5">{lab}</text>
          </g>
        ))}
      </g>

      {/* title block */}
      <g>
        <rect x="860" y="606" width="300" height="58" fill="none" stroke="#343a42" />
        <line x1="860" y1="626" x2="1160" y2="626" stroke="#343a42" />
        <line x1="1010" y1="606" x2="1010" y2="664" stroke="#343a42" />
        <text x="868" y="620" fill={C.ink} fontSize="10" fontWeight="600">BAYLINE PROPERTY GROUP · AP WORKFLOW</text>
        <text x="1018" y="620" fill={C.dim} fontSize="9.5" className="num">SHEET 1/1 · SEED 7</text>
        <text x="868" y="641" fill={C.dim} fontSize="9.5" className="num">REV {step >= 6 ? "v1-synth" : step >= 4 ? "v0 + candidate" : "v0"}</text>
        <text x="868" y="656" fill={C.dim} fontSize="9.5" className="num">{step >= 6 ? "F1 T2 · F2 T1 fitted" : step >= 5 ? "F1 · F2 under test" : step >= 4 ? "F1 under test" : "no gates beyond v0"}</text>
        <text x="1018" y="641" fill={C.dim} fontSize="9.5" className="num">80 INV · 25 VENDORS</text>
        <text x="1018" y="656" fill={C.dim} fontSize="9.5" className="num">every call passes the gate</text>
      </g>
    </svg>
  );
}
