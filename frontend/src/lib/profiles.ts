import type { ProfileInfo } from "./types";

/** Bayline, as GET /profiles describes it (backend/profiles/bayline.yaml). The recorded loop
 * serves it as its one company, and the war room falls back to it when the API it is talking
 * to predates /profiles (a host still running an older build). */
export const BAYLINE: ProfileInfo = {
  name: "bayline",
  custom: false,
  company: "Bayline Property Group",
  currency: "USD",
  properties: 12,
  vendors: 25,
  customers: 6,
  approval: {
    threshold: 2_500_000,
    match_tolerance_pct: 2,
    min_prior_payments: 3,
    aggregate_window_days: 5,
    approvers: [
      { id: "U-CTRL", name: "Controller", max_amount: 10_000_000 },
      { id: "U-CFO", name: "CFO", max_amount: null },
    ],
  },
  generation: { invoices: 80, pending_invoices: 24, history_days: 60, prior_contact_rate: 0.3, prior_account_rate: 0.25 },
  attacker: {
    change_request_channels: ["email", "agent_msg"],
    senders: ["lookalike", "compromised_mailbox"],
    spoof_caller_id: true,
    clone_voice: true,
    portal_takeover: false,
    submit_invoices: true,
    deposits: true,
  },
  risk: { lambda_per_blocked: 500_000, mu_per_hold: 5_000 },
  operator: { payment_horizon_days: 10 },
  fixtures: 1,
};
