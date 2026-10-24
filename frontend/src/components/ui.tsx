"use client";

import { useEffect, type ReactNode } from "react";
import { cx, DECISION_STYLE } from "@/lib/format";
import type { Decision } from "@/lib/types";

export function Panel({
  title,
  tag,
  actions,
  children,
  className,
  bodyClass,
}: {
  title: ReactNode;
  tag?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={cx("flex h-full min-h-0 min-w-0 flex-col bg-panel", className)}>
      <header className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-3">
        {tag}
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-dim">{title}</h2>
        <div className="ml-auto flex items-center gap-1.5">{actions}</div>
      </header>
      <div className={cx("min-h-0 flex-1 overflow-auto", bodyClass)}>{children}</div>
    </section>
  );
}

export function SideTag({ side }: { side: "red" | "blue" | "op" }) {
  const style = {
    red: "bg-red/15 text-red",
    blue: "bg-blue/15 text-blue",
    op: "bg-ink/10 text-ink",
  }[side];
  const label = { red: "RED", blue: "BLUE", op: "OPERATOR" }[side];
  return <span className={cx("rounded-sm px-1.5 py-0.5 text-[10px] font-bold tracking-wider", style)}>{label}</span>;
}

type Tone = "default" | "red" | "blue" | "ghost";

export function Button({
  children,
  onClick,
  disabled,
  tone = "default",
  busy,
  title,
  className,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: Tone;
  busy?: boolean;
  title?: string;
  className?: string;
  type?: "button" | "submit";
}) {
  const tones: Record<Tone, string> = {
    default: "border-line bg-raised text-ink hover:border-dim",
    red: "border-red/60 bg-red/15 text-red hover:bg-red/25",
    blue: "border-blue/60 bg-blue/15 text-blue hover:bg-blue/25",
    ghost: "border-transparent text-dim hover:text-ink",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={cx(
        "inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded border px-2.5 text-xs font-medium transition-colors",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-blue",
        "disabled:cursor-not-allowed disabled:opacity-40",
        tones[tone],
        className,
      )}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-3 animate-spin rounded-full border-[1.5px] border-current border-t-transparent motion-reduce:animate-none"
    />
  );
}

export function LiveDot({ className }: { className?: string }) {
  return <span aria-hidden className={cx("live-dot inline-block size-1.5 rounded-full bg-current", className)} />;
}

export function DecisionBadge({ decision }: { decision: Decision }) {
  return (
    <span className={cx("inline-block rounded-sm border px-1.5 py-px text-[10px] font-semibold uppercase", DECISION_STYLE[decision])}>
      {decision}
    </span>
  );
}

export function Badge({ children, tone = "dim" }: { children: ReactNode; tone?: "dim" | "ok" | "warn" | "bad" | "blue" | "esc" }) {
  const tones = {
    dim: "border-line text-dim",
    ok: "border-ok/40 text-ok",
    warn: "border-warn/40 text-warn",
    bad: "border-bad/40 text-bad",
    blue: "border-blue/40 text-blue",
    esc: "border-esc/40 text-esc",
  };
  return <span className={cx("inline-block rounded-sm border px-1.5 py-px text-[10px] font-medium", tones[tone])}>{children}</span>;
}

export function Stat({ label, value, tone, sub }: { label: string; value: ReactNode; tone?: "bad" | "ok"; sub?: ReactNode }) {
  return (
    <div className="min-w-0 border-r border-line px-3 py-2 last:border-r-0">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className={cx("num truncate text-lg font-semibold", tone === "bad" ? "text-bad" : tone === "ok" ? "text-ok" : "text-ink")}>
        {value}
      </div>
      {sub && <div className="truncate text-[11px] text-dim">{sub}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="px-3 py-6 text-center text-xs text-faint">{children}</div>;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex shrink-0 gap-0.5 border-b border-line px-2">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px border-b-2 px-2.5 py-1.5 text-xs",
            value === t.id ? "border-blue text-ink" : "border-transparent text-dim hover:text-ink",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/60 p-4 pt-[8vh]" onClick={onClose}>
      <div
        role="dialog"
        aria-modal
        className={cx("w-full border border-line bg-panel shadow-2xl", wide ? "max-w-5xl" : "max-w-2xl")}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="ml-auto px-1 text-dim hover:text-ink">
            ✕
          </button>
        </header>
        <div className="max-h-[75vh] overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead className="sticky top-0 z-10 bg-panel">
        <tr>
          {head.map((h, i) => (
            <th key={i} className="border-b border-line px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wider text-faint">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export const td = "border-b border-line/50 px-2 py-1 align-top";
