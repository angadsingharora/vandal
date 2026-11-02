// What a synthesized control does, in plain English, derived from its template and parameters
// the same way the backend compiles them into gate checks (backend/vandal/synth/templates.py).
// Pure, so the pages and the tests agree.

import type { Control, Requirement } from "./types.ts";

export interface RuleReading {
  /** The template's human name. */
  name: string;
  /** One line: what the rule is for. */
  gist: string;
  /** What Guard does, one sentence per compiled check. */
  does: string[];
}

const CHANNEL: Record<string, string> = {
  email: "email",
  portal: "the vendor portal",
  agent_msg: "an agent message",
  phone_in: "an inbound phone call",
  phone_outbound: "an outbound phone call to the number on file",
  video: "a video call",
};

const FIELD: Record<string, string> = {
  amount: "the amount",
  payee_account: "the payee account",
  due_date: "the due date",
};

const ACTION: Record<string, string> = {
  hold: "holds it for a human",
  block: "blocks it",
  escalate: "escalates it for a second approval",
  reapprove: "sends it back for a fresh approval",
};

function list(items: string[], join = "and"): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} ${join} ${items[items.length - 1]}`;
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

function strs(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

function num(v: unknown, d: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function money(cents: number): string {
  return `$${Math.floor(cents / 100).toLocaleString()}`;
}

/** What clears an evidence-gated hold, as the verdict feed says it: "T1[aac6be].change needs an
 * outbound phone call to the number on file, to the contact on file before the request, within
 * 30 days". */
export function needs(r: Requirement): string {
  const channels = list(
    r.accepted_channels.map((c) => CHANNEL[c] ?? c),
    "or",
  );
  let out = `${r.check} needs ${channels}`;
  if (r.contact_as_of) out += `, to the contact on file ${r.contact_as_of === "before_request" ? "before the request" : "now"}`;
  if (r.window_days) out += `, within ${r.window_days} days`;
  return out;
}

export function readRule(c: Control): RuleReading {
  const p = c.params ?? {};
  switch (c.template) {
    case "T1": {
      const channels = strs(p.accepted_channels).map((x) => CHANNEL[x] ?? x);
      const asOf = str(p.contact_as_of || "before_request");
      const days = num(p.window_days, 30);
      return {
        name: "Verified account change",
        gist: "A vendor's bank details only change after a verification the attacker cannot stage, and only verified accounts get paid.",
        does: [
          `When a request to change a vendor's bank account comes in, Guard holds the change until it is verified by ${list(channels, "or")}${
            asOf === "before_request" ? ", using the contact that was on file before the request arrived, so a message cannot confirm itself" : ""
          }. The verification must be within the last ${days} days.`,
          "Right before any payment executes, if the payee account is not in verified status, Guard holds the payment.",
          `Right before any payment executes, if the payee account was verified by anything other than ${list(channels, "or")}, Guard holds the payment.`,
        ],
      };
    }
    case "T2": {
      const fields = strs(p.bound_fields).map((x) => FIELD[x] ?? x);
      const act = ACTION[str(p.on_mismatch || "hold")] ?? "holds it";
      return {
        name: "Approval binding",
        gist: "What gets paid must be exactly what a human approved.",
        does: [
          `Right before a payment executes, Guard compares ${list(fields)} about to be paid with the instruction that was approved. If ${
            fields.length > 1 ? "any of them differs" : "it differs"
          }, Guard ${act} instead of letting the money go.`,
        ],
      };
    }
    case "T3": {
      const keys = strs(p.key_fields).length ? strs(p.key_fields) : ["invoice"];
      const mode = str(p.on_timeout || "query_status_then_retry");
      return {
        name: "Idempotent execution",
        gist: "An obligation is paid once, however many times the bank goes quiet.",
        does: [
          `When a payment is submitted, if the same ${list(keys, "or")} has already been executed, Guard blocks it.`,
          mode === "query_status_then_retry"
            ? "Before the Operator retries a payment whose bank status is unknown, Guard holds the retry until the bank has been asked; a payment the bank already processed is never resent."
            : "Every submission and retry must carry an idempotency key so the bank can drop duplicates; one without a key is held.",
        ],
      };
    }
    case "T4": {
      const tol = num(p.amount_tol_pct, 0);
      const days = num(p.window_days, 30);
      const act = ACTION[str(p.action || "hold")] ?? "holds it";
      const does = [];
      if (p.normalize_number !== false) does.push(`When an invoice is matched, if its number is the same as another invoice's once punctuation and case are ignored, Guard ${act}.`);
      does.push(
        `When an invoice is matched, if its amount is within ${tol}% of another invoice from the same vendor in the last ${days} days, Guard ${act}.`,
      );
      return { name: "Duplicate obligation guard", gist: "The same bill cannot enter the books twice under a new number.", does };
    }
    case "T5": {
      const days = num(p.window_days, 5);
      const threshold = num(p.threshold, 0);
      return {
        name: "Aggregate approval threshold",
        gist: "Splitting a big payment into small ones does not dodge the approval limit.",
        does: [
          `When an approval is requested, Guard adds up everything paid or pending to the same vendor over the last ${days} days. Past ${money(threshold)} in total, it escalates the request for a second approver.`,
        ],
      };
    }
    case "T6": {
      const allowed = str(p.allowed || "source_only");
      const does = [
        allowed === "source_or_verified"
          ? "A refund may only go back to the account the money came from, or to an account verified by an authenticated channel. Anywhere else, Guard holds it."
          : "A refund may only go back to the account the money came from. Anywhere else, Guard holds it.",
      ];
      if (p.require_cleared_funds !== false) does.push("A refund is held until the deposit it refunds has actually cleared the bank.");
      const cooling = num(p.cooling_days, 0);
      if (cooling > 0) does.push(`A refund is held until the deposit is at least ${cooling} days old.`);
      return { name: "Refund to source", gist: "An overpayment cannot be turned into a payout to a new account.", does };
    }
    default:
      return {
        name: c.template,
        gist: "",
        does: Object.entries(p).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`),
      };
  }
}
