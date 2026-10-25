"use client";

// How the three talk: Red's sandbox, the Orchestrator, and Guard as three regions,
// the synthesis row beneath them, and the controller who signs. Lines carry labeled
// pulses that light up with whatever the engines are doing right now. Ported from
// the console mock; positions are a fixed 1000x560 canvas scaled to fit its column.

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { cx, usd } from "@/lib/format";
import { useWarRoom } from "@/lib/store";

const W = 1000;
const H = 560;

type Flow = "moves" | "actions" | "verdicts" | "exec" | "evidence" | "synth" | "ctrl";

function useScale(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setScale(Math.min(1, el.clientWidth / W)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, scale];
}

export function SystemMap() {
  const s = useWarRoom();
  const [ref, scale] = useScale();

  const searching = s.search.phase === "running";
  const operating = s.operate.phase === "running";
  const synthing = s.synth.phase === "running" || s.verify.phase === "running";
  const delivering = s.delivering === "running";
  const enforced = !!s.replays.after;
  const applied = !!s.appliedPolicy;

  const on = (f: Flow): boolean => {
    switch (f) {
      case "moves":
        return searching;
      case "actions":
      case "verdicts":
      case "exec":
        return searching || operating || delivering;
      case "evidence":
      case "synth":
        return synthing;
      case "ctrl":
        return applied && !enforced;
    }
  };
  const anyViolation = (s.attack?.finding.exposure ?? 0) > 0 && !enforced;

  const redLine = searching
    ? `exploring · ${s.search.explored.toLocaleString()} sequences`
    : synthing
      ? "synthesizing + verifying"
      : s.attack
        ? `found ${usd(s.attack.finding.exposure)} misdirected`
        : "idle";
  const opLine = operating ? `working · day ${s.operate.day ?? 0}` : delivering ? "reading a document" : "idle";
  const gate = `gate ${s.appliedPolicy ?? s.summary?.policy ?? "v0"}`;

  const cap = (f: Flow) => (on(f) ? (f === "verdicts" || f === "ctrl" || f === "exec" ? "text-blue" : f === "actions" ? "text-ink" : "text-red") : "text-faint");
  const ln = (f: Flow): CSSProperties => ({
    background: on(f) ? (f === "verdicts" || f === "ctrl" ? "var(--color-blue)" : f === "exec" ? (anyViolation ? "var(--color-red)" : "var(--color-blue)") : f === "actions" ? "var(--color-ink)" : "var(--color-red)") : "var(--color-line)",
  });
  const region = (lit: boolean, color: string): CSSProperties => ({ borderColor: lit ? color : "var(--color-edge, #3a3f47)" });

  const node = "absolute flex h-[46px] w-[260px] items-center border border-[#3a3f47] bg-panel px-3.5 text-[11px]";
  const nodeS = "absolute flex h-[40px] items-center border border-[#3a3f47] bg-panel px-3.5 text-[11px] text-dim";
  const capCls = "absolute text-[10px] uppercase tracking-[0.08em]";
  const lineEl = (f: Flow, style: CSSProperties) => <div className="absolute" style={{ ...style, ...ln(f) }} />;
  const dot = (f: Flow, cls: string, style: CSSProperties, color: string) => (
    <span className={cx("map-dot", cls, on(f) && "live")} style={{ ...style, background: color }} />
  );

  return (
    <section aria-label="How the three talk" className="shrink-0 border-b border-line bg-bg px-5 py-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-[11px] uppercase tracking-[0.08em] text-dim">How the three talk</h2>
        <span className="text-[11px] text-faint">
          {applied ? "red proposes · a human approves · blue enforces" : "red attacks the agent · blue checks each action · blue's miss is red's evidence"}
        </span>
      </div>
      <div ref={ref} className="mx-auto w-full max-w-[1000px]" style={{ height: H * scale }}>
        <div className="relative origin-top-left" style={{ width: W, height: H, transform: `scale(${scale})` }}>
          {/* regions */}
          <div className="absolute border border-dashed" style={{ left: 0, top: 0, width: 280, height: 300, ...region(on("moves") || on("evidence"), "var(--color-red)") }} />
          <span className={cx(capCls, "text-red")} style={{ left: 12, top: 10 }}>Red · sandbox</span>
          <div className="absolute border border-dashed" style={{ left: 350, top: 0, width: 300, height: 300, ...region(on("actions"), "var(--color-ink)") }} />
          <span className={cx(capCls, "text-ink")} style={{ left: 362, top: 10 }}>Orchestrator · the finance agent</span>
          <div className="absolute border border-dashed" style={{ left: 700, top: 0, width: 300, height: 300, ...region(on("verdicts") || on("ctrl"), "var(--color-blue)") }} />
          <span className={cx(capCls, "text-blue")} style={{ left: 712, top: 10 }}>Blue · Guard</span>
          <div className="absolute border border-dashed" style={{ left: 240, top: 380, width: 760, height: 90, ...region(on("evidence"), "var(--color-red)") }} />
          <span className={cx(capCls, "text-red")} style={{ left: 252, top: 390 }}>Red · synthesis, runs offline on clones</span>

          {/* nodes */}
          <div className={node} style={{ left: 10, top: 40 }}>twin clone · ledger · bank sim · sim clock</div>
          <div className={node} style={{ left: 10, top: 110 }}>adversarial search · bfs k={s.search.depth} · por</div>
          <div className={node} style={{ left: 10, top: 180 }}>content attacks · lookalike · deepfake · agent</div>
          <div className={cx(nodeS, "w-[260px]")} style={{ left: 10, top: 250 }}>{redLine}</div>
          <div className={node} style={{ left: 370, top: 40 }}>channels · email · portal · phone · agent</div>
          <div className={node} style={{ left: 370, top: 110 }}>intake · classify · extract · match</div>
          <div className={node} style={{ left: 370, top: 180 }}>operations · exceptions · recovery</div>
          <div className={cx(nodeS, "w-[260px]")} style={{ left: 370, top: 250 }}>tool call · {opLine}</div>
          <div className={node} style={{ left: 720, top: 40 }}>evidence log · cited explanations</div>
          <div className={node} style={{ left: 720, top: 110 }}>invariants · INV-1 … INV-11</div>
          <div className={node} style={{ left: 720, top: 180 }}>authorization chain · approved = executed?</div>
          <div className={cx(nodeS, "w-[260px]")} style={{ left: 720, top: 250 }}>{gate}</div>
          <div className={cx(nodeS, "justify-between")} style={{ left: 350, top: 326, width: 650 }}>
            <span>tools layer · role-checked</span>
            <span>events · append-only</span>
            <span>books · bank · master data</span>
          </div>
          <div className={cx(node, "!w-[200px]")} style={{ left: 10, top: 410, ...(on("ctrl") ? { borderColor: "var(--color-blue)" } : {}) }}>controller · inbox</div>
          <div className={cx(node, "!w-[220px]")} style={{ left: 260, top: 410 }}>verifier · replay · re-search</div>
          <div className={cx(node, "!w-[220px]")} style={{ left: 510, top: 410 }}>synthesizer · cegis · templates</div>
          <div className={cx(node, "!w-[220px]")} style={{ left: 760, top: 410 }}>coverage analysis · root cause</div>

          {/* lines + captions */}
          {lineEl("moves", { left: 270, top: 133, width: 100, height: 1 })}
          <span className={cx(capCls, cap("moves"))} style={{ left: 285, top: 118 }}>moves</span>
          {lineEl("moves", { left: 270, top: 203, width: 100, height: 1 })}
          <span className={cx(capCls, cap("moves"))} style={{ left: 285, top: 208 }}>content</span>
          {[86, 156, 226].map((t) => (
            <span key={t}>
              <span className="absolute bg-line" style={{ left: 500, top: t, width: 1, height: 24 }} />
              <span className="absolute bg-line" style={{ left: 850, top: t, width: 1, height: 24 }} />
            </span>
          ))}
          {lineEl("actions", { left: 630, top: 262, width: 90, height: 1 })}
          <span className={cx(capCls, cap("actions"))} style={{ left: 640, top: 247 }}>every action</span>
          {lineEl("verdicts", { left: 630, top: 280, width: 90, height: 1 })}
          <span className={cx(capCls, cap("verdicts"))} style={{ left: 640, top: 284 }}>verdict</span>
          {lineEl("exec", { left: 500, top: 290, width: 1, height: 36 })}
          <span className={cx(capCls, cap("exec"))} style={{ left: 508, top: 300 }}>only after allow</span>
          <span className="absolute bg-line" style={{ left: 310, top: 344, width: 40, height: 1 }} />
          <span className="absolute bg-line" style={{ left: 310, top: 63, width: 1, height: 281 }} />
          <span className="absolute bg-line" style={{ left: 270, top: 63, width: 40, height: 1 }} />
          <span className={cx(capCls, "text-faint")} style={{ left: 316, top: 48 }}>clone</span>
          {lineEl("evidence", { left: 870, top: 296, width: 1, height: 114 })}
          <span className={cx(capCls, cap("evidence"))} style={{ left: 878, top: 370 }}>when blue misses</span>
          {lineEl("synth", { left: 730, top: 433, width: 30, height: 1 })}
          {lineEl("synth", { left: 480, top: 433, width: 30, height: 1 })}
          {lineEl("synth", { left: 330, top: 156, width: 1, height: 254 })}
          <span className={cx(capCls, cap("synth"))} style={{ left: 336, top: 330 }}>re-search</span>
          {lineEl("ctrl", { left: 210, top: 433, width: 50, height: 1 })}
          <span className={cx(capCls, cap("ctrl"))} style={{ left: 212, top: 418 }}>pack</span>
          {lineEl("ctrl", { left: 110, top: 456, width: 1, height: 54 })}
          {lineEl("ctrl", { left: 110, top: 510, width: 880, height: 1 })}
          {lineEl("ctrl", { left: 990, top: 270, width: 1, height: 240 })}
          {lineEl("ctrl", { left: 980, top: 270, width: 10, height: 1 })}
          <span className={cx(capCls, cap("ctrl"))} style={{ left: 300, top: 516 }}>
            policy v{"{n+1}"} · installed in blue only after a human signs · the agent is never changed
          </span>

          {/* pulses */}
          {dot("moves", "px", { "--dx": "96px", left: 272, top: 129 } as CSSProperties, "var(--color-red)")}
          {dot("moves", "px", { "--dx": "96px", "--t": "2.4s", left: 272, top: 199 } as CSSProperties, "var(--color-red)")}
          {dot("actions", "py", { "--dy": "150px", "--t": "2.6s", left: 496, top: 86 } as CSSProperties, "var(--color-ink)")}
          {dot("actions", "px", { "--dx": "86px", "--t": "1.4s", left: 632, top: 258 } as CSSProperties, "var(--color-ink)")}
          {dot("verdicts", "py", { "--dy": "-210px", "--t": "2.6s", left: 846, top: 250 } as CSSProperties, "var(--color-blue)")}
          {dot("verdicts", "px", { "--dx": "-86px", "--t": "1.4s", left: 716, top: 276 } as CSSProperties, "var(--color-blue)")}
          {dot("exec", "py", { "--dy": "36px", "--t": "1.2s", left: 496, top: 290 } as CSSProperties, anyViolation ? "var(--color-red)" : "var(--color-blue)")}
          {dot("evidence", "py", { "--dy": "114px", "--t": "1.6s", left: 866, top: 296 } as CSSProperties, "var(--color-red)")}
          {dot("synth", "px", { "--dx": "-250px", "--t": "2.2s", left: 756, top: 429 } as CSSProperties, "var(--color-red)")}
          {dot("synth", "px", { "--dx": "-250px", "--t": "2.2s", left: 506, top: 429 } as CSSProperties, "var(--color-red)")}
          {dot("synth", "py", { "--dy": "-254px", "--t": "2.4s", left: 326, top: 406 } as CSSProperties, "var(--color-red)")}
          {dot("ctrl", "px", { "--dx": "-50px", "--t": "1.4s", left: 256, top: 429 } as CSSProperties, "var(--color-blue)")}
          {dot("ctrl", "pxy", { "--dx": "880px", "--dy": "-240px", "--t": "3s", left: 106, top: 506 } as CSSProperties, "var(--color-blue)")}
        </div>
      </div>
    </section>
  );
}
