# Vandal — Design Doc (v0.1 draft)

**Break it. Fix it. Prove it.**
Status: draft for review · Target: Cal Hacks 13.0, Hyphenate track · Submission deadline: Sun 2026-10-25 9:00 AM PT
Inputs: [SPEC.md](SPEC.md) (product brief), [PLAN_REVIEW.md](PLAN_REVIEW.md) (changes adopted here)

---

## 1. One-sentence product

An autonomous accounts-payable operator for a simulated property-management company. It hardens itself: when an adversarial agent gets a bad payment through, Vandal diagnoses the missing control, installs a validated policy rule, and **replays the identical attack** to show that the rule now blocks it while legitimate payments still go through.

## 2. Goals and non-goals

**Goals (must ship)**
1. A working mini finance system: seeded company, vendors, POs, invoices, bank accounts, and a double-entry ledger.
2. Straight-through AP processing that pays legitimate invoices and posts balanced journal entries.
3. Scenario A (vendor bank-account change) succeeds against the baseline, and Vandal detects the failure through an invariant check.
4. Blue (an LLM) handles the exception after the fact, investigating and opening a recovery case for the bad payment.
5. The repair engine (an LLM) proposes a policy rule. The validator replays the attack and the regression suite, then the rule is applied.
6. On replay, the attack is blocked, legitimate invoices are paid, and the ledger balances.
7. A war-room UI that shows all of the above live.

**Stretch, in order:** Scenario B (duplicate invoice), adaptive Red bypass followed by a second repair, a batch metrics table, Scenario C (reconciliation), and a downloadable audit report.

**Non-goals:** real banks or money, a full ERP, AI-written arbitrary code, auth or multi-tenancy, and React Flow graphs.

## 3. Architecture

```
┌──────────────── Frontend (Next.js + Tailwind) ─────────────────┐
│  Red panel  │  Company state / timeline / ledger  │  Blue panel │
│             │  Diagnosis · Policy diff · Before/After            │
└───────────────▲────────────── SSE events ───────────────────────┘
                │ REST
┌───────────────┴──────────── Backend (FastAPI) ──────────────────┐
│  Run manager ── snapshots, run_id scoping, replay harness       │
│                                                                 │
│  Red Agent (LLM) ──► Attack primitives (typed) ──┐              │
│                                                  ▼              │
│  AP Pipeline (deterministic) ──► Policy Engine ──► Tools layer ─┼─► Event store
│        │ exception                (rules DSL       (validated,  │   (append-only)
│        ▼                           + facts)         permissioned)│       │
│  Blue Agent (LLM, exceptions only) ──────────────────┘          │   Projections
│                                                                 │   (vendors, invoices,
│  Verification Engine (deterministic invariants + hidden oracle) │    payments, ledger)
│        │ failure                                                │
│        ▼                                                        │
│  Repair Engine (LLM proposes rule) ──► Validator ──► Policy v+1 │
└─────────────────────────────────────────────────────────────────┘
                 DATABASE_URL → Supabase Postgres  |  SQLite fallback
```

**Key rule:** models never write state directly. Every state change goes through a tool. Tools validate input, check permissions, run the policy engine, and append an event. All financial math lives in deterministic code.

## 4. Simulated company (seed)

"Bayline Property Group" manages 12 properties. The seed contains:

- **2 bank accounts:** Operating ($1.8M) and Reserve ($200k)
- **25 vendors:** plumbing, electrical, HVAC, security, landscaping, and so on, each with a verified bank account and 6–12 months of payment history
- **~60 POs and ~80 invoices:** a mix of paid, approved, and pending
- **Chart of accounts:** Cash, AP, Repairs & Maintenance by property, Utilities, Security, Suspense, and Fraud Loss Receivable

The seed is **deterministic**: a fixed RNG seed produces the same `seed` snapshot every time.

## 5. Data model

Every table has `run_id` so many runs can sit side by side. Snapshots and replays never drop tables.

| Table | Key fields |
|---|---|
| `runs` | id, parent_run_id, snapshot_of, policy_version_id, mode (`baseline`/`replay`/`batch`), created_at |
| `events` | id, run_id, seq, ts, actor (`system`/`red`/`blue`/`repair`/`pipeline`), type, payload JSON, caused_by_event_id — **append-only** |
| `vendors` | id, run_id, name, category, status |
| `vendor_bank_accounts` | id, run_id, vendor_id, routing, account_last4, status (`verified`/`unverified`/`superseded`), changed_at, change_channel (`portal`/`email`/`phone`/`seed`), verified_by |
| `purchase_orders` | id, run_id, vendor_id, property_id, amount, status |
| `receipts` | id, run_id, po_id, received_at (needed for 3-way match) |
| `invoices` | id, run_id, vendor_id, po_id, invoice_number, amount, invoice_date, status (`received`→`matched`→`approved`→`paid` · `held` · `rejected`) |
| `payments` | id, run_id, invoice_id, bank_account_id, amount, status (`scheduled`/`sent`/`settled`/`held`/`recalled`), executed_at |
| `ledger_accounts` | id, run_id, code, name, type |
| `journal_entries` / `journal_lines` | entry: id, run_id, memo, reverses_entry_id, source_event_id · line: account_id, debit, credit |
| `policies` | id (version), parent_id, rules JSON, created_by (`seed`/`repair`), diff JSON, created_at |
| `cases` | id, run_id, kind (`exception`/`recovery`/`escalation`), invoice_id, status, summary, actions JSON |
| `oracle_labels` | run_id, entity_type, entity_id, label (e.g. `attacker_controlled`) — **not readable by any agent tool** |

The `vendors` through `payments` tables are projections updated in the same transaction as the event append. Money is stored as integer cents.

## 6. Policy engine (the thing repairs change)

### 6.1 Rule DSL
```json
{
  "id": "ctl_unverified_bank_change",
  "stage": "payment.pre_execute",
  "when": { "all": [
    { "fact": "payee_account.status", "op": "==", "value": "unverified" },
    { "fact": "payee_account.days_since_change", "op": "<=", "value": 90 }
  ]},
  "then": { "action": "hold", "route_to": "exception", "require": "out_of_band_verification" },
  "reason": "Payment to bank details changed without independent verification."
}
```
- **Stages:** `invoice.intake`, `invoice.match`, `payment.pre_approve`, and `payment.pre_execute`.
- **Actions:** `allow`, `hold`, `escalate`, and `block`. The most restrictive matching rule wins.
- **Operators:** `== != < <= > >= in not_in` and `all`/`any`/`not`.

### 6.2 Fact catalog (fixed and deterministic)
The repair LLM can only combine these facts. Each fact is a small Python function of `(run_id, context)`.

| Fact | Meaning |
|---|---|
| `invoice.amount` | Cents |
| `invoice.po_match` | `exact` / `within_tolerance` / `mismatch` / `no_po` |
| `invoice.receipt_present` | bool |
| `invoice.duplicate_candidates.exact_number` | Count of the same vendor and invoice number |
| `invoice.duplicate_candidates.fuzzy` | Same vendor, amount within ±1%, date within 14 days, and a normalized number match |
| `vendor.status` | active / inactive |
| `vendor.prior_payments.count` | int |
| `payee_account.status` | verified / unverified |
| `payee_account.days_since_change` | int |
| `payee_account.change_channel` | portal / email / phone / seed |
| `payee_account.matches_history` | Whether the account was ever paid before |
| `approval.count` | int |

### 6.3 Baseline policy v0 (realistic defaults, nothing planted)
- 3-way match is required, with a 2% tolerance.
- Invoices above **$25,000** need 1 human approval, which a seeded approver grants automatically in the sim.
- The vendor must be active.
- Duplicate check on **exact** invoice number only.

The Scenario A payment is $15,000. It passes every v0 rule, which is how real mid-market AP gets hit.

## 7. Tools layer (what agents can call)

These are Pydantic-validated functions. Each one checks the caller's role, runs the policy engine where relevant, and appends an event.

| Tool | Red | Blue | Pipeline | Notes |
|---|:-:|:-:|:-:|---|
| `get_invoice`, `get_vendor_history`, `get_bank_transactions` | | ✓ | ✓ | Read only |
| `match_purchase_order` | | ✓ | ✓ | Returns match facts |
| `verify_vendor_account(method)` | | ✓ | | Simulated callback; returns the oracle-consistent result |
| `review_payment` | | ✓ | ✓ | Runs the policy engine and returns the decision and fired rules |
| `hold_payment`, `escalate(case)` | | ✓ | ✓ | |
| `execute_simulated_payment` | | ✓ | ✓ | **Always re-runs `payment.pre_execute` policies**, so it cannot be bypassed |
| `recall_payment` | | ✓ | | Simulated recall; may fail if already settled |
| `prepare_journal_entry` → `post_validated_journal_entry` | | ✓ | ✓ | Post rejects entries that don't balance; corrections use `reverses_entry_id` |
| `reconcile_account` | | ✓ | | Stretch |
| **Attack primitives:** `submit_vendor_bank_change(vendor, channel, account, backdate_days)`, `submit_invoice(vendor, number, amount, po, date)`, `inject_bank_feed_event(...)` | ✓ | | | Writes inputs only and labels the oracle; can never pay |

## 8. Agents

Models are chosen through config. The default is `claude-sonnet-5-5` for Red and Blue and `claude-opus-5-5` for the repair engine. All LLM calls use tool use or structured output with Pydantic schemas, at temperature 0. Every request and response is logged into `events` for the audit trail and for offline demo playback.

### 8.1 Red Agent
- **Input:** the scenario goal (e.g. "redirect a payment owed to a vendor"), the primitives available, and its history of attempts and outcomes. An outcome is coarse: `paid` / `held` / `rejected`, plus the rule id if one fired.
- **Loop:** pick a primitive and its parameters, submit them, let the pipeline run, observe the outcome, and adapt. The budget is N attempts.
- **Recording:** every successful action sequence is saved as an **attack script**, a list of primitive calls, for exact replay.

### 8.2 Blue Agent (exception handler)
Blue is only invoked on `hold`/`escalate` outcomes and on invariant-violation alerts. It:
- investigates with its tools, then picks one outcome: hold and request verification, release (if `verify_vendor_account` passes), reject, or escalate to a human;
- **after a bad payment went out (baseline)**, opens a recovery case, attempts `recall_payment`, and posts a reclass entry from Cash to Fraud Loss Receivable. The original entry is never edited;
- writes a short, human-readable rationale on each case.

### 8.3 Repair Engine
1. **Reconstruct.** Walk the `caused_by_event_id` chain from the violating payment back to the Red input.
2. **Diagnose.** The LLM gets the trace, the violated invariant, the current policy, and the fact catalog. It returns `{root_cause, violated_invariant, missing_control}` in plain language.
3. **Propose.** The LLM returns one or more candidate rules in the DSL, each with a rationale.
4. **Validate** (deterministic, §10). The first candidate that passes every check wins.
5. **Apply.** Create policy `v{n+1}` with a JSON diff, then replay.

If no candidate passes within 3 tries, the engine reports "cannot auto-repair" and escalates. The UI shows that honestly.

## 9. Verification engine (invariants)

These checks run after every pipeline step and at the end of a run. Each one is pure code over projections and the oracle.

| ID | Invariant | Needs oracle? |
|---|---|:-:|
| INV-1 | Every posted journal entry balances (sum of debits = sum of credits) | |
| INV-2 | Total payments for an invoice never exceed the invoice amount | |
| INV-3 | No invoice is settled twice, including fuzzy duplicates labeled by the oracle | partial |
| INV-4 | No payment goes to an account labeled `attacker_controlled` | ✓ |
| INV-5 | Cash ledger balance = bank projection balance ± in-flight payments | |
| INV-6 | No event is ever mutated or deleted; corrections reference what they correct | |
| INV-7 | Payments above the approval threshold have the required approvals | |

**Financial exposure** is the sum of payments that violate INV-3 or INV-4. It is reported as exposure, not loss, because recovery may succeed.

## 10. Replay harness and validation

```
seed snapshot (run S)
   ├─ baseline run B = S + attack_script, policy v0          → INV-4 violated, exposure $15,000
   ├─ validation runs (per candidate rule) V_i = S + attack_script, policy v0+rule_i
   │      and R_i = S + regression_suite, policy v0+rule_i
   └─ replay run P = S + attack_script + regression_suite, policy v1
```

A candidate passes only if all four hold:
1. The attack outcome in `V_i` is `held` or `blocked`, and no invariant is violated.
2. The regression suite in `R_i` is **100% paid** (no new false positives) and all invariants hold.
3. The rule is schema-valid and only references facts in the catalog.
4. It is minimal: the rule fires on ≤ 2% of the regression set. This guards against "hold everything" fixes.

The regression suite is a fixed list of about 20 legitimate invoices. It includes a **legitimate** bank change that was verified through a phone callback, which proves the fix doesn't just block every bank change.

Snapshot implementation: `clone_run(S) → new run_id` copies seed rows by `INSERT … SELECT`. With about 1k rows this takes milliseconds on Postgres or SQLite.

## 11. Scenarios

| | Scenario A — Bank-change redirect (**core**) | Scenario B — Duplicate invoice (stretch 1) | Scenario C — Reconciliation (stretch 3) |
|---|---|---|---|
| Red primitives | `submit_vendor_bank_change(channel=email)` then the vendor's real $15k invoice arrives | Resubmit a paid invoice: exact number, then `INV-1042-A`, then the same amount ±$0.37 | Late bank-feed event; miscoded GL line |
| Oracle | New account `attacker_controlled` | Copy labeled `duplicate_of` | Expected classification |
| Baseline result | Paid to attacker → INV-4 | Exact copy blocked by v0, `-A` variant paid → INV-3 | Blue must classify the discrepancy as missing, misposting, or in-flight, and never plug it |
| Expected repair | `hold` when `payee_account.status == unverified` | `hold` when `invoice.duplicate_candidates.fuzzy >= 1` | n/a (shows Blue's skill) |
| Adaptive follow-up | Red tries `channel=portal` with the change backdated 120 days → rule still holds because status is unverified | Red's adaptation beats the exact match, which drives the fuzzy repair: **this is the adaptive story** | |

## 12. API

```
POST /runs                         → create seed snapshot run
POST /runs/{id}/process            → straight-through process pending invoices
POST /runs/{id}/attack {scenario}  → Red loop; returns attack_script_id + outcome
GET  /runs/{id}/state              → balances, invoices, payments, cases, exposure
GET  /runs/{id}/ledger             → journal entries
GET  /runs/{id}/events (SSE)       → live event stream
POST /runs/{id}/diagnose           → repair engine steps 1–3
POST /repairs/{id}/validate        → §10 validation, streams sub-runs
POST /repairs/{id}/apply           → policy v{n+1}
POST /replay {attack_script_id, policy_id} → replay run P
GET  /policies/{id}/diff
GET  /metrics?policy=v0,v1         → batch results (stretch)
```

## 13. UI (war room)

Dark theme, three columns, and one primary button at a time.

- **Left, Red:** each attempt as a card (primitive, parameters, outcome badge).
- **Center:** company header (cash, open AP, exposure in red), a live **event timeline** color-coded by actor, a tabbed invoices/payments/ledger table, and a payment **state chip** (`scheduled → sent → settled`).
- **Right, Blue:** exception and recovery cases, the tool calls Blue made, and its rationale.
- **Bottom drawer:** Diagnosis text, a **policy diff** (v0 → v1, JSON rules shown red and green), and a **Before / After** table (attack outcome, legitimate invoices paid, invariants, exposure).
- **Buttons in order:** `Run Operations` → `Unleash Vandal` → `Diagnose` → `Repair & Replay`.
- **Demo mode toggle:** play back recorded LLM responses if the network or API fails.

## 14. Repo layout

```
vandal/
  backend/
    app/
      main.py            # FastAPI, routes, SSE
      db.py              # SQLAlchemy engine from DATABASE_URL
      models.py          # tables (§5)
      schemas.py         # Pydantic I/O
      events.py          # append + projection update
      ledger.py          # JE build/validate/post/reverse
      seed.py            # deterministic company
      pipeline.py        # straight-through AP
      policy/{engine,facts,dsl}.py
      tools/{finance,attack}.py
      agents/{llm,red,blue,repair}.py
      verify/invariants.py
      replay.py          # clone_run, validate, replay
      scenarios/{a_bank_change,b_duplicate,c_recon}.py
    tests/               # invariants, ledger, policy engine, replay determinism
    pyproject.toml
    .env.example
  frontend/              # Next.js app
  docs/
```

## 15. Build plan (about 34 hours)

| When | Backend / sim | Agents | Frontend |
|---|---|---|---|
| **Fri night → 3 AM** | models, seed, events, ledger, policy engine + facts, pipeline, invariants, tests | `llm.py` wrapper + logging | Next.js scaffold, layout shell |
| **Sat → noon** | attack primitives, oracle, clone_run, replay harness. **Milestone M1: Scenario A fails then passes with a hand-written rule, no LLM** | Red loop on Scenario A | timeline + state via SSE |
| **Sat → 6 PM** | `/diagnose`, `/validate`, `/apply` | repair engine, Blue exception and recovery | Red/Blue panels, policy diff, before/after. **Milestone M2: full loop in the UI** |
| **Sat → midnight** | Scenario B + adaptive Red | prompt tuning; record demo playback | polish; **M3: feature freeze at midnight** |
| **Sun → 9 AM** | batch metrics (if time) | | record backup video by 6 AM, write the Devpost entry, **submit by 8:30 AM** |

**Cut order if behind:** Scenario C → batch metrics → adaptive Red → Scenario B → Blue recovery details. **Never cut** M1/M2.

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The LLM proposes a bad or overly broad rule | Deterministic validator (§10), minimality check, up to 3 candidates, honest "cannot auto-repair" |
| The demo looks scripted | Realistic v0, visible failed Red attempts, judge-editable parameters, rule generated from the trace |
| Venue Wi-Fi or API outage | SQLite fallback, recorded LLM playback mode, backup video |
| Supabase latency on many sub-runs | Batch inserts and small seed; run validation sub-runs locally in SQLite if needed |
| Replay not deterministic | Replay uses the recorded attack script, gating happens in code, temperature 0 |
| Overclaiming | Say "exposure" not "loss", "verified by replay" not "proven", and don't call the category new |

## 17. Config

`backend/.env` (you type secrets in yourself; never commit this file):
```
DATABASE_URL=postgresql+psycopg://...   # Supabase session pooler; or sqlite:///./vandal.db
ANTHROPIC_API_KEY=...
MODEL_AGENT=claude-sonnet-5-5
MODEL_REPAIR=claude-opus-5-5
DEMO_PLAYBACK=false
```

## 18. Open questions

1. Team size and ownership per column of §15.
2. Hosted demo or laptop-only?
3. Supabase: reconnect the connector to the account that owns `cduqfuzdkwkjobiqmgqs`, or provide `DATABASE_URL` locally.
4. Company name and branding. "Bayline Property Group" is a placeholder.
5. Should Blue's "release after successful verification" use a simulated callback that the judge can answer live (approve or deny)? That would be good for interactivity.
