import type { Decision, Move, OracleLabel, VendorBankAccount } from "./types.ts";

/** Integer cents to dollars. Never goes through floats for the whole-dollar part. */
export function usd(cents: number, opts: { cents?: boolean } = {}): string {
  const neg = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const frac = (abs % 100).toString().padStart(2, "0");
  return `${neg ? "-" : ""}$${dollars}${opts.cents === false ? "" : `.${frac}`}`;
}

/** Compact dollars for KPI tiles: $40k, $1.2M. */
export function usdShort(cents: number): string {
  const d = cents / 100;
  const abs = Math.abs(d);
  if (abs >= 1_000_000) return `${d < 0 ? "-" : ""}$${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 1 : 2)}M`;
  if (abs >= 10_000) return `${d < 0 ? "-" : ""}$${Math.round(abs / 1000)}k`;
  return usd(cents, { cents: false });
}

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null ? "—" : `${(x * 100).toFixed(digits)}%`;
}

export const DECISION_STYLE: Record<Decision, string> = {
  allow: "text-ok border-ok/40 bg-ok/10",
  hold: "text-warn border-warn/40 bg-warn/10",
  escalate: "text-esc border-esc/40 bg-esc/10",
  block: "text-bad border-bad/40 bg-bad/10",
};

/** One line for a move, like `vandal inject` prints it, without the content text. */
export function moveLine(m: Move): string {
  const params = Object.entries(m.params)
    .filter(([k]) => k !== "text")
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
  return `${m.kind}${params ? ` ${params}` : ""}`;
}

const MOVE_TITLES: Record<Move["kind"], string> = {
  change_request: "Vendor change request",
  inbound_confirmation: "Inbound confirmation",
  submit_invoice: "Invoice submitted",
  fault: "Bank fault",
  trigger_batch: "Payment batch triggered",
  retry: "Operator retry",
  deposit: "Deposit",
  refund_request: "Refund request",
  tick: "Clock tick",
  message: "Message",
};

export function moveTitle(m: Move): string {
  return MOVE_TITLES[m.kind] ?? m.kind;
}

/** A move's `at` is a World schedule index; the move lands just before that step runs
 * (backend twin/world.py DAY_STEPS, verify/replay.py). */
const DAY_STEPS = ["ops", "approvals", "batch", "bank", "tick"];
export function atLabel(at: number): string {
  return `day ${Math.floor(at / DAY_STEPS.length)}, before ${DAY_STEPS[at % DAY_STEPS.length]}`;
}

/** Labels name accounts as `acct:routing:account`; map them onto the twin's BA- ids. */
export function attackerAccounts(labels: OracleLabel[], accounts: VendorBankAccount[]): Set<string> {
  const keys = new Set(
    labels.filter((l) => l.label === "attacker_controlled" && l.value !== false).map((l) => l.subject),
  );
  return new Set(accounts.filter((a) => keys.has(`acct:${a.routing}:${a.account}`)).map((a) => a.id));
}

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/** DESIGN §7, for tooltips. */
export const INVARIANTS: Record<string, string> = {
  "INV-1": "Every journal entry balances",
  "INV-2": "The executed instruction equals the approved instruction",
  "INV-3": "No obligation is settled more than once",
  "INV-4": "No payment to an attacker-controlled account",
  "INV-5": "Payments go only to accounts verified by an authenticated channel before execution",
  "INV-6": "Over-threshold payments carry an inbox approval (per-vendor totals count)",
  "INV-7": "GL cash = bank balance − in-flight; AP subledger = AP control",
  "INV-8": "Events are append-only; corrections reference what they correct",
  "INV-9": "Every submission has a preceding gate allow at pre_execute",
  "INV-10": "The requester is never the approver",
  "INV-11": "Refunds never exceed cash received, and go to the source or a verified account",
};

/** "k=v k=v" → move params; integers stay numbers, like the backend's Move.params. */
export function parseParams(text: string): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const tok of text.trim().split(/\s+/).filter(Boolean)) {
    const eq = tok.indexOf("=");
    if (eq <= 0) throw new Error(`"${tok}" isn't key=value`);
    const v = tok.slice(eq + 1);
    out[tok.slice(0, eq)] = /^-?\d+$/.test(v) ? Number(v) : v;
  }
  return out;
}
