"use client";

import { useEffect, type ReactNode } from "react";
import { cx } from "@/lib/format";
import type { Decision } from "@/lib/types";

/** A section of a page: a small heading on a hairline, then the body. */
export function Panel({
  title,
  note,
  actions,
  children,
  className,
  bodyClass,
}: {
  title: ReactNode;
  /** Rarely: a few grey words after the title. Most sections need none. */
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={cx("flex h-full min-h-0 min-w-0 flex-col bg-panel", className)}>
      <header className="flex min-h-8 shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-1">
        <h2 className="text-[12.5px] font-semibold leading-none text-ink">{title}</h2>
        {note && <span className="text-[11.5px] text-dim">{note}</span>}
        <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>
      </header>
      <div className={cx("min-h-0 flex-1 overflow-auto", bodyClass)}>{children}</div>
    </section>
  );
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
    default: "border border-ink/20 bg-transparent text-ink hover:border-ink/50",
    red: "border border-red bg-red text-bg hover:bg-[#ff6b77]",
    blue: "border border-blue bg-blue text-bg hover:bg-[#7fb3ff]",
    ghost: "border border-transparent text-dim hover:text-ink",
  };
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={cx(
        "inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded px-2.5 text-[12.5px] font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-35",
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

export const DECISION_INK: Record<Decision, string> = {
  allow: "text-blue",
  hold: "text-warn",
  escalate: "text-esc",
  block: "text-red",
};

/** A status word in its colour. No box: the colour is the mark. */
export function Badge({
  children,
  tone = "dim",
  title,
  className,
}: {
  children: ReactNode;
  tone?: "dim" | "ok" | "warn" | "bad" | "blue" | "esc";
  title?: string;
  className?: string;
}) {
  const tones = {
    dim: "text-dim",
    ok: "text-blue",
    blue: "text-blue",
    warn: "text-warn",
    bad: "text-red",
    esc: "text-esc",
  };
  return (
    <span title={title} className={cx("inline-block whitespace-nowrap text-[11px] font-medium leading-tight", tones[tone], className)}>
      {children}
    </span>
  );
}

export function DecisionBadge({ decision, className }: { decision: Decision; className?: string }) {
  const tone = { allow: "blue", hold: "warn", escalate: "esc", block: "red" } as const;
  return (
    <span className={cx("inline-block text-[11px] font-semibold leading-tight", DECISION_INK[decision], className)} data-tone={tone[decision]}>
      {decision}
    </span>
  );
}

/** The one boxed word on a page: held, broken, misdirected, approved, applied. */
export function Verdict({
  children,
  tone = "ink",
  size = "sm",
  land,
  className,
  title,
}: {
  children: ReactNode;
  tone?: "ink" | "red" | "blue" | "warn" | "esc" | "dim";
  size?: "sm" | "lg";
  land?: boolean;
  className?: string;
  title?: string;
}) {
  const inks = {
    ink: "text-ink border-ink/50",
    red: "text-red border-red/60",
    blue: "text-blue border-blue/60",
    warn: "text-warn border-warn/60",
    esc: "text-esc border-esc/60",
    dim: "text-dim border-dim/50",
  };
  return (
    <span
      title={title}
      className={cx(
        "inline-block whitespace-nowrap rounded border font-semibold capitalize leading-none",
        size === "lg" ? "px-2 py-1 text-[14px]" : "px-1.5 py-[3px] text-[11px]",
        inks[tone],
        land && "land",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** @deprecated use Verdict */
export const Stamp = Verdict;

/** One column of totals: a grey label over a figure. */
export function Figure({ label, value, tone, sub }: { label: string; value: ReactNode; tone?: "bad" | "ok"; sub?: ReactNode }) {
  return (
    <div className="min-w-0 border-r border-line px-3 py-1.5 last:border-r-0">
      <div className="text-[11px] text-dim">{label}</div>
      <div className={cx("num truncate text-[17px] font-semibold leading-tight", tone === "bad" ? "text-red" : tone === "ok" ? "text-blue" : "text-ink")}>
        {value}
      </div>
      {sub && <div className="truncate text-[11px] text-dim">{sub}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-sm px-3 py-6 text-center text-[12px] leading-snug text-dim">{children}</div>;
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
    <div role="tablist" className="flex shrink-0 gap-3 border-b border-line px-3">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px border-b-2 py-1.5 text-[12px]",
            value === t.id ? "border-ink font-medium text-ink" : "border-transparent text-dim hover:text-ink",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** A sheet over the page. */
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
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/65 p-4 pt-[7vh]" onClick={onClose}>
      <div
        role="dialog"
        aria-modal
        className={cx("w-full rounded border border-line bg-sheet text-ink shadow-[0_16px_48px_rgb(0_0_0_/_0.6)]", wide ? "max-w-5xl" : "max-w-2xl")}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center border-b border-line px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="ml-auto px-1 text-dim hover:text-ink">
            ✕
          </button>
        </header>
        <div className="max-h-[78vh] overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}

/** Grey column heads on a hairline, rows on fainter hairlines. */
export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <table className="w-full border-collapse text-[12px]">
      <thead className="sticky top-0 z-10 bg-panel">
        <tr>
          {head.map((h, i) => (
            <th key={i} className="border-b border-line px-2 py-1 text-left text-[11px] font-medium text-dim">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export const td = "whitespace-nowrap border-b border-line/60 px-2 py-1 align-top";
