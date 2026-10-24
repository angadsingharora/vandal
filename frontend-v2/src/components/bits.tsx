"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "@/lib/format";

/** Animate a number toward its target (count-up), for hero tiles. */
export function useCountUp(target: number, ms = 700): number {
  const [value, setValue] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    if (a === target) return;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      setValue(Math.round(a + (target - a) * e));
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

export type Tone = "ink" | "red" | "blue" | "ok" | "amber" | "dim" | "esc";
const TEXT: Record<Tone, string> = {
  ink: "text-ink",
  red: "text-red",
  blue: "text-blue",
  ok: "text-ok",
  amber: "text-amber",
  dim: "text-dim",
  esc: "text-esc",
};

export function Hero({
  label,
  value,
  sub,
  tone = "ink",
  className,
  glow,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  className?: string;
  glow?: "red" | "ok" | "blue";
}) {
  return (
    <div className={cx("glass rounded-xl px-4 py-3", glow && `glow-${glow}`, className)}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-faint">{label}</div>
      <div className={cx("display num mt-0.5 text-[28px] font-semibold leading-none", TEXT[tone])}>{value}</div>
      {sub && <div className="mt-1 text-[11px] text-dim">{sub}</div>}
    </div>
  );
}

export function Chip({ children, tone = "dim", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  const ring: Record<Tone, string> = {
    ink: "border-line2 text-ink",
    red: "border-red/50 bg-red/10 text-red2",
    blue: "border-blue/50 bg-blue/10 text-blue2",
    ok: "border-ok/50 bg-ok/10 text-ok",
    amber: "border-amber/50 bg-amber/10 text-amber",
    dim: "border-line text-dim",
    esc: "border-esc/50 bg-esc/10 text-esc",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium", ring[tone], className)}>
      {children}
    </span>
  );
}

export function Cta({
  children,
  onClick,
  tone = "blue",
  busy,
  disabled,
  title,
  big,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "red" | "blue" | "ok" | "ghost";
  busy?: boolean;
  disabled?: boolean;
  title?: string;
  big?: boolean;
  className?: string;
}) {
  const tones = {
    red: "bg-red text-[#1a0308] hover:bg-red2 glow-red",
    blue: "bg-blue text-[#021018] hover:bg-blue2 glow-blue",
    ok: "bg-ok text-[#02160c] hover:brightness-110 glow-ok",
    ghost: "border border-line2 text-ink hover:border-dim bg-raised/60",
  };
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-all",
        big ? "h-11 px-5 text-sm" : "h-8 px-3 text-xs",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none",
        tones[tone],
        className,
      )}
    >
      {busy && <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  );
}

export function Section({ title, right, children, className }: { title: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("glass rounded-xl", className)}>
      <header className="flex items-center gap-2 border-b border-line px-4 py-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-dim">{title}</h3>
        <div className="ml-auto flex items-center gap-2">{right}</div>
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-sm text-faint">{children}</div>;
}

export const MOVE_ICON: Record<string, string> = {
  change_request: "✉",
  inbound_confirmation: "☎",
  message: "💬",
  submit_invoice: "🧾",
  fault: "⚡",
  trigger_batch: "▶",
  retry: "↻",
  deposit: "⬇",
  refund_request: "↩",
  tick: "⏱",
};
