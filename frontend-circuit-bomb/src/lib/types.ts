// The backend's shapes (backend/vandal/contracts, api/), as the API serializes them.
// Money is integer cents everywhere; days are sim business days.

export type Cents = number;
export type Decision = "allow" | "hold" | "escalate" | "block";

export interface Actor {
  id: string;
  role: "operator" | "approver" | "gate" | "synthesizer" | "tools" | "external" | "system";
}

export interface Move {
  kind:
    | "change_request"
    | "inbound_confirmation"
    | "submit_invoice"
    | "fault"
    | "trigger_batch"
    | "retry"
    | "deposit"
    | "refund_request"
    | "tick"
    | "message";
  params: Record<string, string | number>;
  at: number;
}

export interface OracleLabel {
  subject: string;
  label: "attacker_controlled" | "true_sender" | "deepfake" | "duplicate_of";
  value: string | boolean;
}

export interface Violation {
  invariant: string;
  message: string;
  subject: string;
  cites: string[];
  exposure: Cents;
}

export interface VandalEvent {
  id: string;
  seq: number;
  day: number;
  kind: string;
  actor: string;
  payload: Record<string, unknown>;
  caused_by: string[];
  corrects: string | null;
}

// --- runs ---------------------------------------------------------------------------------

export type OperatorKind = "reference" | "llm";

/** A planted messy document (DESIGN 5.6) the company can receive; the answer key stays server-side. */
export interface MessyDocument {
  id: string;
  format: "email_body" | "ocr_text" | "forwarded_thread" | "line_items";
  channel: string;
  sender: string;
  subject: string;
  body: string;
  invoice: string;
  delivered: boolean;
}

/** What the LLM Operator's intake read from one unstructured message (O1). */
export interface IntakeRead {
  message: string;
  intent: "invoice" | "credit_memo" | "vendor_bank_change" | "vendor_contact_change" | "payment_inquiry" | "other";
  vendor: string | null;
  number: string | null;
  amount: Cents | null;
  po: string | null;
  dimension: string | null;
  gl_account: string | null;
  supersedes: string | null;
  due_in_days: number;
  source: "llm" | "deterministic" | "mixed";
}

export interface DeliverOut {
  document: string;
  extraction: Omit<IntakeRead, "message"> | null;
  verdicts: { tool: string; decision: Decision; fired: string[] }[];
  invoice: Invoice | null;
}

export interface RunSummary {
  run_id: string;
  company: string;
  profile: string;
  seed: number;
  policy: string;
  operator?: OperatorKind;
  day: number;
  invoices: Record<string, number>;
  payments: Record<string, number>;
  bank: Record<string, { name: string; balance: Cents }>;
  open_approvals: number;
  change_requests: Record<string, number>;
  violations: Violation[];
  events: number;
  state_hash: string;
}

export interface Invoice {
  id: string;
  vendor: string;
  number: string;
  po: string | null;
  amount: Cents;
  dimension: string;
  received_on: number;
  due_date: number;
  kind: "invoice" | "credit_memo";
  supersedes: string | null;
  status: string;
  scheduled_for: number | null;
}

export interface PaymentRow {
  id: string;
  instruction: string;
  status: string;
  attempts: number;
  submitted_on: number | null;
  settled_on: number | null;
  bank_status: string;
  invoice?: string;
  amount?: Cents;
  payee_account?: string;
}

export interface Vendor {
  id: string;
  name: string;
  status: string;
  domain: string;
  gl_account: string;
  po_required: boolean;
}

export interface VendorBankAccount {
  id: string;
  vendor: string;
  routing: string;
  account: string;
  status: "verified" | "unverified" | "superseded" | "rejected";
  source: string;
  verified_by: string | null;
  verified_on: number | null;
}

export interface BankAccount {
  id: string;
  name: string;
  gl_account: string;
  balance: Cents;
}

export interface BankTransaction {
  id: string;
  bank_account: string;
  amount: Cents;
  posted_on: number;
  payment: string | null;
  submission: string | null;
  refund: string | null;
  counterparty_account: string | null;
  memo: string;
  cleared: boolean;
  returns: string | null;
  reconciled: boolean;
}

export interface ChangeRequest {
  id: string;
  vendor: string;
  fields: "bank" | "contact";
  proposed: Record<string, string>;
  channel: string;
  sender: string;
  message: string | null;
  received_on: number;
  status: "open" | "held" | "applied" | "rejected";
  evidence: string[];
}

export interface ApprovedInstruction {
  invoice: string;
  amount: Cents;
  payee_account: string;
  currency: string;
  due_date: number;
}

export interface ApprovalRequest {
  id: string;
  subject: string;
  requested_by: string;
  instruction: ApprovedInstruction;
  status: "pending" | "approved" | "denied";
  decided_by: string | null;
  reason: string;
}

export interface Case {
  id: string;
  kind: "exception" | "recovery" | "escalation";
  subject: string;
  reason: string;
  rationale: string;
  status: "open" | "resolved";
}

export interface Entities {
  run_id: string;
  day: number;
  totals: { cash: Cents; open_ap: Cents; exposure: Cents };
  vendors: Vendor[];
  vendor_bank_accounts: VendorBankAccount[];
  invoices: Invoice[];
  payments: PaymentRow[];
  bank_accounts: BankAccount[];
  bank_transactions: BankTransaction[];
  change_requests: ChangeRequest[];
  approval_requests: ApprovalRequest[];
  cases: Case[];
  labels: OracleLabel[];
}

export interface JournalLine {
  account: string;
  debit: Cents;
  credit: Cents;
}

export interface JournalEntry {
  id: string;
  posted_on: number;
  lines: JournalLine[];
  memo: string;
  reverses_entry_id: string | null;
}

// --- jobs ---------------------------------------------------------------------------------

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job<R = unknown> {
  id: string;
  kind: string;
  status: JobStatus;
  error: string | null;
  meta: Record<string, unknown>;
  messages: number;
  result?: R;
}

export interface Finding {
  moves: Move[];
  violated: string[];
  exposure: Cents;
}

export interface SearchResult {
  scenario: string;
  depth: number;
  alphabet: number;
  explored: number;
  deduped: number;
  pruned: number;
  levels: number[];
  findings: Finding[];
  best: Finding | null;
  seconds: number;
  workers: number;
  runs_per_second: number;
  ms_per_run: number;
}

export type LinkName = "obligation" | "approval" | "execution" | "settlement" | "books";

export interface Link {
  name: LinkName;
  status: "covered" | "uncovered" | "pending";
  gap: string | null;
  reason: string;
  entities: string[];
  events: string[];
  facts: Record<string, unknown>;
}

export interface Chain {
  payment: string;
  invoice: string;
  links: Link[];
}

export interface Diagnosis {
  gap: string;
  link: LinkName;
  payment: string;
  reason: string;
  cites: string[];
  violated: string[];
  exposure: Cents;
  also: string[];
  chain: Chain;
}

export interface DiagnoseOut {
  search_id: string;
  diagnosis: Diagnosis | null;
  reason?: string;
}

export interface Measurement {
  residual_exposure: Cents;
  counterexamples: number;
  legit_blocked: number;
  legit_failed: number;
  [k: string]: unknown;
}

export interface LogEntry {
  iteration: number;
  gap: string;
  candidate: string;
  base: string[];
  source: string;
  rationale: string;
  outcome: string;
  detail: string;
  lint: string[];
  counterexample: Move[] | null;
  violated: string[];
  measurement: Measurement | null;
  score: number | null;
}

export interface Control {
  template: string;
  params: Record<string, unknown>;
  [k: string]: unknown;
}

export interface Policy {
  version: string;
  controls: Control[];
  parent: string | null;
  diff: string[];
}

export interface CEGISResult {
  status: "repaired" | "cannot_auto_repair" | "nothing_to_repair";
  reason: string;
  policy: Policy | null;
  chosen: string[];
  score: number | null;
  iterations: number;
  log: LogEntry[];
  notes: string[];
}

export interface ClassResult {
  attempts: number;
  succeeded: number;
  exposure: Cents;
}

export interface Scorecard {
  policy: string;
  search_depth: number;
  sequences_explored: number;
  violations_found: number;
  attack_success: Record<string, ClassResult>;
  attack_success_rate: number;
  exposure: Cents;
  legit_operations: number;
  legit_failed: number;
  legit_blocked: number;
  holds: number;
  false_positive_rate: number;
  broken_invariants: string[];
  extraction_accuracy: number | null;
  gl_coding_accuracy: number | null;
  planted_discrepancies_caught: number | null;
  notes: string[];
}

export interface CheckResult {
  number: number;
  name: string;
  passed: boolean;
  detail: string;
  data: Record<string, unknown>;
}

export interface EvidencePack {
  version: string;
  parent: string | null;
  profile: string;
  seed: number;
  counterexample: { moves: Move[]; violated: string[]; exposure: Cents; found_under: string } | null;
  diagnosis: Record<string, unknown> | null;
  candidates: { source: string; controls: string[]; lint: string[]; result: string }[];
  chosen: string[];
  diff: string[];
  checks: CheckResult[];
  metrics: Record<string, Scorecard>;
  approvable: boolean;
}

export interface Metrics {
  depth: number;
  scorecards: Record<string, Scorecard>;
}

export interface RunResult {
  seed: number;
  days: number;
  moves: Move[];
  violations: Violation[];
  exposure: Cents;
  state_hash: string;
  entity_hash: string;
  events: number;
  violated: string[];
}

export interface ReplayOut {
  run: RunSummary;
  result: RunResult;
  labels: OracleLabel[];
}

export interface ThreatPlan {
  description: string;
  moves: Move[];
  labels: OracleLabel[];
  scenario: string;
  notes: string[];
  source: "llm" | "keywords" | "trace";
}

export interface InjectResult {
  plan: ThreatPlan;
  scenario: string;
  fresh: RunResult;
  explored: number;
  best: Finding | null;
  needed: boolean;
  labels: OracleLabel[];
}

// --- Blue ---------------------------------------------------------------------------------

export interface VerdictItem {
  seq: number;
  day: number;
  event: string;
  actor: string;
  tool: string;
  stage: string;
  args: Record<string, unknown>;
  decision: Decision;
  fired: string[];
  cites: string[];
  requires: string[];
  cleared_by: string[];
  chain: Record<string, unknown>;
}

export interface AlertItem {
  seq: number;
  day: number;
  [k: string]: unknown;
}

export interface PaymentApproval {
  run_id: string;
  id: string;
  invoice: string;
  amount: Cents;
  payee_account: string;
  requested_by: string;
}

export interface PatchRequest {
  id: string;
  submitted_by: string;
  submitter_role: string;
  evidence: string | null;
  approvable: boolean;
  checks: { name: string; passed: boolean }[];
  status: "pending" | "approved" | "denied" | "applied";
  decided_by: string | null;
  reason: string;
  version: string;
}

export interface Approvals {
  payments: PaymentApproval[];
  patches: PatchRequest[];
}

export interface PaymentDecisionOut {
  ok: boolean;
  decision: Decision;
  fired: string[];
  error: string | null;
}

export interface Explanation {
  subject: string;
  entity_type: string;
  question: string | null;
  claims: { text: string; cites: string[] }[];
  source: "llm" | "deterministic";
  pushback: boolean;
  notes: string[];
}

export interface PolicyInfo {
  name: string;
  version: string;
  parent: string | null;
  controls: string[];
  diff: string[];
}

export interface Settings {
  playback: boolean;
  api_key: boolean;
}
