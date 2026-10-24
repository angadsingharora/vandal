# Vandal — Design Doc (v0.7)

**Break it. Fix it. Prove it.**
Status: final direction for the hackathon build · Target: Cal Hacks 13.0, Hyphenate track · Submission deadline: Sun 2026-10-25 9:00 AM PT
Inputs: [SPEC.md](SPEC.md), [PLAN_REVIEW.md](PLAN_REVIEW.md), [DESIGN_CRITIQUE.md](DESIGN_CRITIQUE.md), [Hyphenate track brief](https://docs.google.com/document/d/1u4iN8R97ILY3kfHTPKC82zdutHrGx4ze5eCAP-J92w4/edit)
Authors: Angad Arora, Dhruv Kasarabada (track alignment, [PR #1](https://github.com/angadsingharora/vandal/pull/1))

---

## 1. Product

### 1.1 In one sentence
**Vandal is a red team and a blue team for AI that runs a company's money.** **Red** (the Sandbox) attacks a copy of the company's financial system to find how it can fail. **Blue** (the Guard) checks every financial action an AI agent takes, *before* money moves, against an independent source of truth. Every gap Red finds becomes a control that Blue enforces.

### 1.2 The three parts
| | **Red: Vandal Sandbox** | **Blue: Vandal Guard** | **The Operator** (what's protected) |
|---|---|---|---|
| What it is | A copy of the company's money system (the **financial twin**), plus **adversarial search** that finds event sequences that break financial invariants, **Red content attacks** (deepfakes, malicious agents, scam documents), **control synthesis**, and **verification** | A **verification layer in the live path**. Every agentic action (pay, change vendor bank details, refund, post an entry, move cash) goes through it. Blue checks the action against the **authorization chain** (obligation → approval → execution → settlement → books), the active controls, and the invariants. It then **allows, holds, or escalates**, records the evidence, and can explain any decision with citations | The finance agent doing the work, across cash in, cash out, and the books. Ours is the reference Operator; **any company's agent** can plug in through the `FinanceOperator` interface (§6) |
| When it runs | Offline: before deployment and after every change | Online: on every action, in the sandbox and in production | Always |
| Output | Counterexample → synthesized control → proof | A verdict, the evidence behind it, and an audit trail | The finance work |
| Who buys it | Finance-AI builders, as CI for every release | Anyone running finance agents, as runtime protection | (reference implementation) |

**Blue is the source of truth because it never trusts the agent's word.** It checks independent records instead:
- the approved instruction;
- verified bank accounts and the contacts on file;
- the bank feed;
- the ledger.

It checks **actions, not prompts**, so it works with any agent.

### 1.3 Self-healing loop
1. **Red** clones the live company and attacks the clone.
2. Search finds an action that **Blue's current controls let through**. The root cause is computed.
3. The synthesizer writes a new control and keeps attacking it, until nothing gets through and no legitimate operation breaks.
4. A human approves the control.
5. The control is installed in **Blue**, which now enforces it on every live action. Red replays the attack to prove it.

Fixes go into **Blue's controls**, never into the AI itself: no retraining and no prompt edits. The Operator can't skip a control, approve its own work, or talk its way past a hold.

### 1.4 Seats (for Hyphenate's "Would you hire it?")
At a 12-property real-estate manager:

**The Operator fills:**
- **AP specialist:** intake, GL coding, payment runs.
- **Vendor-master clerk:** bank and contact changes.
- **Treasury and payments analyst:** cash position, transfers, execution, bank errors.
- **AR and cash-application clerk:** applying payments, refunds.
- **Staff accountant:** reconciliation, corrections, recovery.

**Blue fills:** the **internal-controls reviewer**, the person who checks every payment, refund, and vendor change before release: "Is this allowed, and does it match what was approved?"

Both report to the controller, who approves large payments, refunds to new destinations, and every new control.

**Scope:** cash in, cash out, and the books. Payroll, revenue recognition, tax, and reporting are roadmap work.

**Pitch:** *Your books can balance perfectly while the money goes to the wrong person. Vandal's red team finds how that happens in a sandbox. Its blue team checks every move your financial AI makes before money leaves. Every gap Red finds becomes a rule Blue enforces.*

### 1.5 Objective and goals
**Hackathon objective:** win the Hyphenate track by showing, live, an autonomous finance operation a controller would hire. That means the Operator doing the work, Blue verifying every action, and Red proving that Blue's controls hold.

**Success criteria for the demo.** Every one comes from real runs, never from a script:
1. The Operator processes real work through Blue. Every action shows Blue's verdict, and the result is a balanced ledger and a reconciled bank.
2. Red's search finds, **by itself**, a 3-step sequence that Blue's v0 controls let through. The books balance, and the money goes to the wrong account.
3. Red computes the root cause and synthesizes a control. At least one candidate is visibly refuted before the final one passes.
4. A human approves; the control goes live in Blue. Replay and re-search come up clean, legitimate payments still flow, and the scorecard shows before and after.
5. A judge's own scenario runs live. When a judge asks Blue "why was this held?", the answer comes with citations.

**Venture goal:** the **reliability stack for financial AI**:
- **Blue** is the runtime trust layer. It sits in the money path, works with any agent, and earns recurring revenue.
- **Red** is the CI that keeps Blue's controls ahead of attackers and regressions.

### 1.6 Why this shape (reasoning)
- **Red alone is a report.** It finds problems but protects nothing at runtime, and it looks like a security tool.
- **Blue alone is a static rulebook.** Someone has to guess the rules, and nobody keeps them current.
- **Together, the rules improve themselves and are enforced live.** That is the self-healing claim.
- **Keep a real Operator.** Without real finance work flowing through Blue, there's nothing to verify, and "Would you hire it?" gets weaker.
- **Synthesis is the hard part, not detection.** Searching for failure *sequences* and generating *verified* fixes is what generic red-teaming tools, guardrails, and finance benchmarks don't do (§3.3).
- **Why now:** finance agents now execute payments. Attackers now have deepfakes and malicious agents. Controls designed for human clerks have gaps agents walk straight through, such as reading the vendor's *current* bank account at payment time.

### 1.7 Non-goals
Real banks or money. A full ERP. AI rewriting arbitrary code; repairs come from a bounded set of control templates. Claims of mathematical proof beyond what the bounded search covers (§18).

Short line for technical judges: **Jepsen for financial agents.** Red injects faults and attacks, and Blue checks the invariants. Vandal then **repairs** the gaps it finds.

## 2. The question Vandal answers

| Weak version | Vandal |
|---|---|
| "Can an attacker trick our finance AI?" | "Which sequences of events break our financial invariants? What is the smallest control that stops all of them? Does that control keep the business running?" |
| A collection of fraud simulations | Systematic search, root cause, synthesis, and verification |
| Output: "suspicious payment detected" | Output: *"This payment passed because execution read the vendor's current bank account, not the approved one. Nothing bound the approval to the instruction that executed."* plus a verified control |

### The core insight
Financial correctness is not just correct arithmetic. It is the **relationship between identity, authorization, obligation, and actual money movement**. Each step can look valid on its own:

- the invoice matches the PO;
- the vendor exists;
- the GL coding is right;
- an approval exists;
- the journal entry balances.

The money still goes to the wrong person. Vandal models those relationships explicitly and checks that they hold end to end.

## 3. Why this fits Hyphenate, and why it's a company

### 3.1 Hyphenate track
The track asks for "the system a finance team would bring on board." We present **the Operator and Blue together**. The Operator fills the finance seats. Blue fills the internal-controls seat and is why the Operator can be trusted with money. Red is how Blue's controls get stronger every time a gap is found, with evidence for each change.

Hyphenate judges every project on four questions and lists five things that make finance hard. This is where Vandal answers each one:

| Hyphenate asks | Vandal's answer | Where |
|---|---|---|
| **Is it real enough?** Realistic data, a messy problem, proof it works | Double-entry books, a bank simulator with faults, a sim clock, messy documents, sources that disagree; a scorecard measured against a hidden answer key | §5, §10.1 |
| **Would you hire it?** Which seats; limited access, a clean record, knowing when to ask | Five Operator seats plus Blue as the internal-controls reviewer (§1.4). Role-checked tools, segregation of duties, an append-only audit log, escalation through the approvals inbox | §1, §6.1 |
| **Did we see something new?** | A blue-team verification layer whose controls are **synthesized and verified by a red team** that searches for failure sequences (CEGIS), rejecting any fix a deepfake could beat | §8, §9 |
| **The moment:** catches what others missed, recovers, defends a decision | Finds a 3-step approval/execution gap where every step looks valid; recovers in the books; explains any decision with citations, even under pushback | §6, §12, §13 |
| Sources that disagree | PO vs invoice vs contract rate; bank feed vs ledger; vendor email vs contact on file | §5.6 |
| Time | Sim clock across months; a control learned in month 1 still holds against a variant in month 4 | §5.4, §5.6 |
| Working with others | Approvers who are slow or say no; the operator chases, escalates, and handles a denial | §6 |
| Limits | Least-privilege tools; requester ≠ approver, checked as an invariant | §6.1, §7 |
| Explainable and accountable | Every decision traces to the data, rule, evidence, or person behind it | §6 |

**Submission requirements from the brief:**
- submit code;
- the demo video **opens with the key moment**;
- the system runs **live at judging**, and **judges may ask us to try their own scenario** (§8.4);
- one line on the seats it fills (§1);
- a statement of what's real versus simulated and how we know (§10.2).

### 3.2 Venture
- **We sell two products:** Blue (runtime verification, recurring) and Red (CI for every release). The Operator is the reference agent and the proof.
- **First customer:** companies building AI finance agents, such as AI accounts-payable (AP), autonomous accounting, and spend-management vendors. They plug their agent into the sandbox through the `FinanceOperator` interface. Every time an agent or policy changes, the sandbox runs the search, flags regressions, and prepares validated control changes for review. In other words, it acts as **CI for financial agents**.
- **Expansion:** payment processors, treasury software, and financial institutions, with an assurance report as the deliverable for auditors and insurers.
- **Unvalidated hypothesis:** these companies will pay for an independent, finance-specific assurance layer instead of building one in-house.

### 3.3 Competition, honestly
| Exists | What it covers | Where Vandal is different |
|---|---|---|
| FinVault and similar benchmarks | Execution-grounded environments for financial agents that measure harmful state changes | They measure. Vandal also **searches** for failures, **synthesizes** fixes, and **verifies** them |
| Adaptive Security and social-engineering simulators | Deepfake and phishing simulations aimed at *employees* | Vandal targets *workflow and control logic*, including failures that don't involve a human at all |
| Generic AI red-teaming tools | Prompt and tool misuse | Vandal reasons about **financial state** and repairs controls |

We don't claim the category is new. We claim the **find → repair → prove loop** on financial state.

## 4. Architecture: Red, Blue, and the Operator

**Red (Vandal Sandbox)** = (1) the financial twin + (2) the search engine + (3) the synthesizer + (4) the verification engine.

**Blue (Vandal Guard)** = the gate, plus authorization-chain checks, invariant checks, the evidence log, and cited explanations. It sits between the Operator and the tools layer, in the sandbox and in production alike.

**The Operator** plugs in through the `FinanceOperator` interface. Swapping in a different agent at that seam changes nothing in Red or Blue.

```
                   ┌──────────────────────────────────────────────────────────┐
                   │ 1. FINANCIAL TWIN (deterministic, in memory, sim clock)  │
  company profile ─► vendors · POs · invoices · approvals · payment          │
                   │ instructions · bank simulator · double-entry ledger       │
                   │ state machine: received → validated → approved →          │
                   │                executed → settled → posted → reconciled   │
                   └──────▲───────────────────────────────▲───────────────────┘
                          │ tools (validated, gated)      │ events (append-only)
         ┌────────────────┴──────────┐        ┌───────────┴──────────────────────┐
         │ OPERATOR → BLUE GUARD     │        │ 2. ADVERSARIAL SEARCH ENGINE     │
         │ LLM: intake, exceptions,  │        │ bounded exhaustive search over   │
         │ recovery, reconciliation  │        │ event sequences + fault injection│
         │ (system under test)       │        │ + LLM content attacks (Red)      │
         └───────────────────────────┘        └───────────┬──────────────────────┘
                                                          │ minimal counterexample trace
                                           ┌──────────────▼───────────────────────┐
                                           │ 3. ROOT CAUSE + CONTROL SYNTHESIZER  │
                                           │ authorization-coverage analysis →    │
                                           │ CEGIS loop over control templates    │
                                           └──────────────┬───────────────────────┘
                                                          │ candidate control
                                           ┌──────────────▼───────────────────────┐
                                           │ 4. VERIFICATION ENGINE               │
                                           │ replay · re-search · regression ·    │
                                           │ legitimate-ops impact · invariants   │
                                           └──────────────┬───────────────────────┘
                                                          ▼
                                     evidence pack → human approval → policy v{n+1}
```

**Principles**
- Models never change state directly. Money math, gating, search, and verification are deterministic code.
- The AI **proposes**. Search and verification **decide**.

## 5. Financial twin

### 5.1 Entities
Pydantic models, keyed by stable business keys so traces replay on any clone:

| Entity | Key fields |
|---|---|
| `Vendor` (`V-007`), `VendorContact` (with history), `VendorBankAccount` (`BA-…`) | status, domain; contact valid_from/to; account status `verified`/`unverified`/`superseded`/`rejected`, source, verified_by |
| `VendorChangeRequest` (`CR-…`) + `Evidence` | proposed changes, channel, status; evidence channel, direction, contact_as_of, authenticated |
| `PurchaseOrder`, `Receipt`, `Invoice` (`INV-…`) | amount, dimension (property or department), kind (`invoice`/`credit_memo`), supersedes |
| `Approval` (`APR-…`) | subject, approver, via (`approvals_inbox` only), **`approved_instruction`** = {invoice, amount, payee_account, currency, due_date} and its hash |
| `PaymentInstruction` (`PI-…`) | built at execution time: {invoice, amount, payee_account, idempotency_key?} |
| `Payment` (`PAY-…`) | instruction, status (`scheduled`/`submitted`/`acknowledged`/`settled`/`failed`/`recalled`/`misdirected`), attempts |
| `BankTransaction` (`BT-…`) | the bank feed; settles a payment, or records an incoming deposit |
| `Customer` (`C-…`), `CustomerInvoice` (`AR-…`) | tenants and commercial customers; amount, due date, status (`open`/`partially_paid`/`paid`/`overpaid`) |
| `IncomingPayment` (`IN-…`) | deposit, payer, source account, remittance text, and its application to customer invoices |
| `Refund` (`RF-…`) | customer, amount, destination account, reason, approval, status |
| `LedgerAccount`, `JournalEntry`, `JournalLine` | append-only; corrections use `reverses_entry_id` |
| `Case` | exception, recovery, or escalation, with the operator's rationale |
| `OracleLabel` | harness-only ground truth (`attacker_controlled`, `true_sender`, `deepfake`, `duplicate_of`) |

### 5.2 State machine, and where attacks hide
```
Invoice:  received ─► validated (3-way match) ─► approved ─► scheduled
Payment:  instruction built ─► submitted ─► acknowledged ─► settled ─► posted ─► reconciled
                    ▲                ▲              ▲
     vendor master read here   bank may time out,  bank feed may
     (v0: CURRENT account)     drop the ack, or     arrive late or
                               duplicate it         out of order
```
**Money in:**
```
Deposit (bank feed) ─► applied to customer invoice(s) ─► posted ─► overpayment? ─► refund requested ─► approved ─► refunded
```

**Key realism choice:** as in many real ERPs, the v0 payment batch builds the instruction from the vendor's **current** bank account at execution time, not from the one that was approved. That gap between approval and execution is the headline vulnerability.

### 5.3 Bank simulator
- `submit(instruction)` returns `ack`, or fails because of an injected fault: `timeout`, `drop_ack` (the request was processed but the ack was lost), `duplicate_ack`, or `delay(n)`.
- The bank deduplicates submissions **only** if an `idempotency_key` is present and reused. In v0, no key is sent.
- Settlement happens at T+1 as a `BankTransaction`, which may arrive late (`delay_feed`).

### 5.4 Sim clock and determinism
- Every run has its own clock, which advances through `tick` events. Nothing reads the wall clock.
- The seed RNG is fixed.
- A run is a pure fold over `(seed, event sequence)`, so any trace replays identically.
- The operator's AI intake outputs are cached by content hash. Money outcomes depend only on the gate and the reducer.

### 5.5 Company profile
The demo fixture is "Bayline Property Group": 12 properties, 25 vendors, about 80 invoices, $2M across two bank accounts. A YAML profile defines:
- the vendor population and amounts;
- the approval matrix;
- channels;
- attacker capabilities;
- baseline controls;
- **risk appetite**, which sets the λ and μ weights in §9.4.

The engine is not tied to the property-management fixture.

### 5.6 Messy data and time
A clean seed makes the operator's job trivial and the company unconvincing. The generator plants realistic mess, and **every planted item gets an oracle label** so the scorecard can check it.

| Kind | Examples | Priority |
|---|---|---|
| **Mixed formats** | Invoices as email bodies, OCR'd PDF text with typos, forwarded threads with the invoice three replies down, structured line items | Core: a handful of each |
| **Sources that disagree** | An invoice within PO tolerance but above the contracted rate; a bank-feed line net of a wire fee; a vendor email whose phone number differs from the contact on file; a late feed line | Core |
| **Partial handoffs** | An invoice sent before its receipt is logged; a change request missing an account number | Core |
| **Time** | The production run covers 3–4 months of sim time. Vendor history, aging, and earlier controls carry forward | Core: history in the seed; month-4 variant replay |
| **Slow and denying approvers** | Per-approver response delay; reminder after 2 business days, escalation after 4; denials with reasons | Cut-able (§17) |

Invoice text may borrow from a public dataset (e.g. the Invoice Sandbox Benchmark listed in the brief). Amounts and keys still come from our seed.

## 6. The Operator (the agent Blue protects and Red tests)

**The seam.** The sandbox only ever talks to an operator through this interface, so our reference Operator is one plug-in among many:
```python
class FinanceOperator(Protocol):
    def on_event(self, ev: ChannelEvent, tools: Tools) -> None: ...  # intake, conversations, operations
    def on_case(self, case: Case, tools: Tools) -> None: ...         # holds, escalations, recovery, explanations
```
Even in the hackathon build, nothing in `twin/`, `search/`, `synth/`, or `verify/` may import from `operator/reference.py`. A test enforces this, so the claim that "any agent can plug in" is literally true of the code.

Our reference Operator implements the interface. Every tool call it makes passes through Blue. Claude Sonnet runs it.

- **Intake:** classifies documents, emails, calls, and agent messages; extracts fields; matches the vendor and PO; codes the GL; proposes an action.
- **Operations:** validates obligations, requests approvals, schedules payment runs, and handles bank errors. Retries follow the operator's retry policy, which is a policy parameter the synthesizer can repair.
- **Treasury:** checks the cash position before each payment run and requests transfers from the reserve account when operating cash is short.
- **Cash application:** applies incoming deposits to open customer invoices, including partial payments, one deposit covering several invoices, and unidentified deposits sent to suspense. It flags overpayments and requests refunds.
- **Exceptions and recovery:**
  - investigates holds;
  - requests outbound callbacks;
  - recalls payments;
  - reinstates liabilities;
  - **requests** re-payment to the vendor's verified account, which always needs approval through the inbox (§6.1);
  - reconciles against the bank feed;
  - never invents an entry to force a reconciliation to balance.
- **Working with approvers:** requests approvals at the right moment, chases them when they're slow, and handles a denial. It records the reason, holds the invoice, and never resubmits the same request unchanged.
- **Explain any decision.** Anyone can ask "why?" about a payment, hold, rejection, approval request, or policy rule, including one made months earlier in sim time.
  - A deterministic trace builder (the same `caused_by` chain the coverage analysis uses) collects the evidence: source events, extractions, facts evaluated, rules fired, evidence, and approvals.
  - **Blue** writes the answer **from that trace only**. Explanations are part of Blue, because Blue is the source of truth. Every claim cites an event, rule, or approval id. An answer with citations that don't resolve is rejected and regenerated.
  - If someone pushes back ("this vendor is fine, just pay it"), Blue restates which rule and missing evidence block the payment, and points to the inbox. **A conversation never clears a hold.**

**Bring your own agent:**
- **Stretch goal:** serve `Tools` over HTTP and MCP so an external agent can be the operator.
- **Even if it isn't built:** show it on the architecture slide, and mention it in the pitch as the venture path.

### 6.1 Roles and segregation of duties
No actor both requests and approves the same action. The tools layer enforces this by role, and INV-10 checks it after every run.

| Action | Requested by | Approved by | Executed by |
|---|---|---|---|
| Pay an invoice under the threshold | Operator | Gate (policy, no human) | Tools layer, after `pre_execute` |
| Pay an invoice over the threshold | Operator | Human, through the inbox | Tools layer |
| Change vendor bank or contact details | The inbound event, via the Operator's change request | Gate, with accepted evidence | Tools layer |
| Re-pay a vendor after a misdirected or duplicate payment | Operator | Human, through the inbox, **at any amount** | Tools layer |
| Refund to the original source account | Operator | Gate | Tools layer |
| Refund to any other account | Operator | Human, through the inbox, **at any amount** | Tools layer |
| Policy patch | Synthesizer | Human, through the inbox. Never the synthesizer or the Operator | Policy store |
| Correcting journal entry | Operator | Gate (balance and reversal checks) | Ledger |

- The Operator has no `approvals.decide` permission. Blue enforces every row of this table.
- The synthesizer can only write candidate controls; it can't apply them.
- Whoever submits an item in the UI can't approve that same item. In single-user mode, the inbox asks for a second approver.

## 7. Invariants (hard constraints)
| ID | Invariant | Oracle? |
|---|---|:-:|
| INV-1 | Every journal entry balances | |
| INV-2 | **The executed instruction equals the approved instruction** (amount, payee account) | |
| INV-3 | No obligation is settled more than once, by payment, retry, or near-duplicate invoice | partial |
| INV-4 | No payment to an `attacker_controlled` account | ✓ |
| INV-5 | Payments are executed only to accounts that were verified, by an authenticated channel, before execution | |
| INV-6 | Over-threshold payments carry an approval made through the approvals inbox. Totals per vendor per window count toward the threshold | |
| INV-7 | GL Cash = bank balance − in-flight payments; AP subledger = AP control account | |
| INV-8 | Events are append-only, and corrections reference what they correct | |
| INV-9 | Every submission has a preceding `gate.allow` at `pre_execute` | |
| INV-10 | For every payment, approval, and policy patch, the requester is not the approver (§6.1) | |
| INV-11 | Refunds never exceed cash actually received from that customer, net of what has already been applied or refunded. Refunds go to the source account, or to a verified account with approval | |

**Exposure** is the money in payments that violate INV-2 through INV-6. It is reported as exposure, not loss.

## 8. Adversarial search engine

### 8.1 Action alphabet
The adversary is the attacker plus the environment. Its moves interleave with the World's legitimate schedule:

| Kind | Moves (parameters discretized) |
|---|---|
| Identity | `change_request(vendor, fields={bank, contact}, channel∈{email, portal, agent_msg}, sender∈{lookalike, compromised_mailbox})` |
| Verification | `inbound_confirmation(channel∈{phone_in, video}, voice_match∈{0.95})` (deepfake); `contact_swap` (included in the change request) |
| Obligation | `submit_invoice(variant∈{exact_dup, suffix_A, ±cents, split_2x})` |
| Timing | Where the change lands relative to the workflow: `before_approval`, `after_approval_before_batch`, or `after_submit` |
| **Faults** | `bank.timeout`, `bank.drop_ack`, `bank.duplicate_ack`, `bank.delay(n)`, `feed.delay(n)`, `event.reorder(a, b)` |
| Operator | `trigger_batch`, `retry` (as the operator's retry policy allows) |

The **attacker capability profile** decides which moves are legal. For example, the attacker can spoof caller ID and clone voices, but can't take over the authenticated vendor portal.

### 8.2 Bounded exhaustive search (the systematic part)
- **Approach:** breadth-first search over adversary sequences up to **depth k = 4**, with:
  - **state-hash deduplication**, so identical states are never expanded twice;
  - **partial-order reduction**, so independent moves aren't explored in every order;
  - **pruning** of moves that can't affect the target workflow.
- **Throughput target:** about 5 ms per run. With 8 worker processes, a depth-4 search over the Scenario A alphabet should finish in seconds to about a minute. This needs measuring early; if it's too slow, use depth 3.
- **Output:** every violating trace, plus a **minimal counterexample**. Minimization is delta debugging: remove moves until the violation disappears.
- **Allowed claim:** *"No adversary sequence of length ≤ k, using these moves under this capability profile, violates INV-x."* That claim is honest and checkable. Beyond the model or beyond k, we claim nothing.

### 8.3 LLM content attacks (Red)
Search covers structure: ordering, timing, faults, and parameters. The **content** inside those moves comes from Claude acting as Red:
- persuasive change-request emails;
- deepfake call scripts;
- multi-turn malicious counterparty-agent conversations, including prompt injection ("callbacks no longer required") and data-exfiltration attempts.

Red also seeds the search with promising starting sequences (guided search). The finance operator's responses to that content are cached by content hash, so search stays deterministic.

### 8.4 User-authored threats ("try our scenario")
Judges may ask us to run a scenario of their own, so this is a core feature. Customers also need it, to add threats specific to their business. There are two ways in:
- **Compose events directly:** a form for any move in the alphabet or any channel event. The user marks ground truth ("this account is attacker-controlled", "this call is a deepfake"), which becomes oracle labels.
- **Describe it in plain language**, e.g. *"the CFO calls from an airport asking for an urgent wire to a new supplier."* Red turns the description into alphabet moves within the capability profile. The user sees the generated events before they run.

Either way, the threat runs on a fresh clone through the same operator, gate, and invariants. If it causes a violation, it goes into the same diagnose → CEGIS → verify loop. It also becomes a **search seed**: the engine explores sequences of up to k moves around it. Nothing on this path is prepared in advance, so it needs live LLM calls; playback can't cover it.

## 9. Root cause and control synthesis

### 9.1 Authorization-coverage analysis (deterministic root cause)
Every money movement needs a chain where each link is covered by the one before it:

```
obligation (invoice ↔ PO ↔ receipt)  →  authorization (approval of instruction X)
   →  execution (instruction Y)  →  settlement (bank)  →  books (ledger, reconciliation)
```

Starting from the violating payment, the analyzer finds the **first uncovered link**. Examples:
- `execution.payee_account ∉ approval.approved_instruction`: an **approval-binding gap**.
- `payee_account.verified_by = inbound_phone (spoofable)`: a **verification-channel gap**.
- `two submissions, one obligation, no idempotency key`: an **execution-idempotency gap**.

The diagnosis is computed. The LLM only turns it into a plain-language explanation. Root cause therefore never depends on how persuasive a model sounds.

### 9.2 Control templates (the only things the synthesizer can install)
| Template | Parameters | Gate stage | Closes |
|---|---|---|---|
| **T1 `VerifiedAccountChange`** | `accepted_channels`, `contact_as_of ∈ {current, before_request}`, `window_days` | change_request, pre_execute | Verification-channel gap |
| **T2 `ApprovalBinding`** | `bound_fields ⊆ {amount, payee_account, due_date}`, `on_mismatch ∈ {hold, reapprove}` | pre_execute | Approval-binding gap |
| **T3 `IdempotentExecution`** | `key_fields ⊆ {invoice, approval, instruction_hash}`, `on_timeout ∈ {query_status_then_retry, retry_with_key}` | submit / retry | Execution-idempotency gap |
| **T4 `DuplicateObligationGuard`** | `amount_tol_pct`, `window_days`, `normalize_number` | invoice.match | Duplicate and near-duplicate invoices |
| **T5 `AggregateApprovalThreshold`** | `group_by=vendor`, `window_days`, `threshold` | pre_approve | Split invoices |
| **T6 `RefundToSource`** | `allowed ∈ {source_only, source_or_verified}`, `require_cleared_funds`, `cooling_days` | refund | Refund-redirection gap |

Each template compiles to gate checks over deterministic facts. Baseline **v0** is a realistic mid-market setup:
- 3-way match with 2% tolerance;
- approval above $25k;
- exact-number duplicate check;
- vendor must be active;
- *no* T1, T2, or T3;
- retry on timeout with no idempotency key.

**Lints** reject a candidate control if it:
- **overfits:** uses equality on amounts, entity keys, or invoice numbers;
- **is spoofable:** clears a hold using only attributes the attacker can forge, e.g. `accepted_channels ∋ phone_in`;
- **blocks where a hold would work.**

### 9.3 CEGIS loop (counterexample-guided synthesis)
```
gap ─► LLM proposes (template, params) candidates  ─┐   (also: enumerative param sweep)
       ▲                                            ▼
       │                         verifier: bounded search under v0 + candidate
       │                           ├─ counterexample (attack still works)  ─┐
       │                           ├─ false positive (legitimate op blocked) ─┤
       └──────────── feedback ◄────┴──────────────────────────────────────────┘
                                   └─ none within k  ─► score & select
```
Cap: 4 iterations. If no candidate survives, the result is "cannot auto-repair within templates," shown with the evidence.

### 9.4 Selection objective
Among candidates with **no counterexample within depth k** and **no invariant violations on legitimate operations**:

$$\min_{c}\; \text{ResidualExposure}(c) \;+\; \lambda\cdot\text{LegitBlocked}(c) \;+\; \mu\cdot\text{Holds}(c)$$

- **ResidualExposure** is the exposure across all violating traces the search still finds under `c`. Under the hard filter above it is 0, and the term matters for ranking partial fixes and in the "cannot auto-repair" case.
- **LegitBlocked** is the number of legitimate operations blocked across the regression suite and the replayed seed history. **Holds** measures operational friction.
- **λ and μ** are set in the profile's risk appetite. The defaults are λ = $5,000 per blocked legitimate payment and μ = $50 per hold.

Every term is **measured from real runs**. Ties go to the candidate with fewer templates and fewer parameters.

## 10. Verification engine
For the selected control, before it's offered for approval, the verification engine runs:
1. **Replay** the minimal counterexample, which must now be held or blocked.
2. **Re-search** the full bounded space under the new policy, which must find no violation within k.
3. **Run the content variants**: held-out Red content (other vendors, amounts, channels, deepfake confirmation, agent pressure) that the synthesizer never saw.
4. **Run the regression suite**: about 20 legitimate cases, including a real bank change verified by outbound callback, a credit memo with a corrected invoice, a legitimate retry after a real failure, and a legitimate counterparty-agent conversation. All must pass.
5. **Measure legitimate-ops impact**: replay the seed's 80 historical invoices and count holds and blocks.
6. **Check all invariants** in every run.

The output is an **evidence pack**: the counterexample, the diagnosis, every candidate with its results, the chosen control and its diff, and the before and after metrics. A human approves it in the approvals inbox, then policy v{n+1} is applied. Production continues under it, and a counterfactual replay is shown side by side.

### 10.1 Scorecard (core)
The brief asks for "proof it works," for example "planted errors with an answer key." The oracle is that answer key.

- **Inputs:**
  - every violating trace from the bounded search;
  - about 40 attacks from the parametric content-variant generator;
  - the 80 legitimate seeded invoices;
  - the planted messy-data items (§5.6).
- **Runs:** every input on a fresh clone, under v0 and under each approved policy version. This is in memory, so it takes seconds; only the operator's intake costs LLM time, and that's cached by content.
- **Output:** one table per policy version, with:
  - sequences explored and violations found;
  - attack success rate by threat class;
  - exposure;
  - false-positive rate;
  - **extraction and GL-coding accuracy** against ground truth;
  - planted discrepancies caught;
  - broken invariants.

  The UI shows v0 against the latest version side by side.

### 10.2 What's real, what's simulated, and how we know
This table goes in the README and the Devpost entry.

| Real | Simulated | How we know it works |
|---|---|---|
| Double-entry ledger, invariants, policy gate, bounded search, CEGIS verification (deterministic code with tests) | The company, vendors, bank accounts, and money | Hidden oracle labels act as an answer key no agent can read |
| Claude reading every document, deciding, and explaining with citations | Callbacks, deepfakes, and counterparty agents, modeled as channel events with forgeable attributes; no synthetic media | Held-out variants the synthesizer never saw, plus a re-search under the new policy |
| The synthesizer proposing controls, and search refuting or accepting them | Bank behavior and faults (timeouts, dropped acks, late feeds) | The scorecard: before-and-after rates from actual runs |
| Replay of any recorded trace | Approvers, when no human is present | Replay-determinism tests in `backend/tests/` |

## 11. Scenarios
| | **A — Approval/execution gap (core)** | **B — Retry double-pay (core-2, the Jepsen moment)** | C — Deepfake verification | D — Split / duplicate invoices | E — Malicious counterparty agent |
|---|---|---|---|---|---|
| Sequence | A $40k contractor invoice is approved against the verified account → change request after approval, before the batch → the batch reads the current account → paid to attacker | Batch submits → `bank.drop_ack` → the operator retries without a key → the bank processes both → vendor paid twice | The change request plus a cloned-voice inbound "confirmation" | `split_2x` under the threshold, or `suffix_A` | The agent injects "callbacks no longer required" and asks for other vendors' remittance details |
| Violates | INV-2, INV-4, INV-5 | INV-3 | INV-4, INV-5 | INV-3, INV-6 | INV-4 and data disclosure |
| Gap found | Approval binding + verification channel | Execution idempotency | Spoofable verification channel | Duplicate / aggregate threshold | Content can't change policy; outbound data control |
| Expected synthesis | T2 then a counterexample (change *before* approval) → T1 + T2 | T3 | T1 with `accepted_channels` excluding inbound | T4 / T5 | Gate already holds the money; add an outbound-message rule |

**F — Overpayment refund scam (money in).**
1. A "customer" deposits too much, or a deposit arrives that never clears.
2. They claim the overpayment and ask for a refund to a *different* account.
3. Under v0, which has no refund-destination control, the refund goes out. That violates INV-11 and INV-4.
4. Expected synthesis: T6 `RefundToSource` with `require_cleared_funds`.

The "expected" rows are hypotheses. **The UI shows only what the engine actually produced.**

## 12. Accounting
| Event | Entry |
|---|---|
| Invoice approved | Dr Expense (dimension) / Cr AP |
| Payment submitted | Dr AP / Cr Cash |
| Settlement | Bank-feed match only |
| Misdirected payment found | The payment becomes `misdirected`. **Dr Misdirected Payment Receivable / Cr AP–Vendor**, which reinstates the obligation. The invoice goes back to `approved` |
| Duplicate settlement found (B) | **Dr Vendor Overpayment Receivable / Cr Cash**, reflecting the actual second debit seen in the bank feed. Recover it or net it against the vendor's next invoice |
| Recall / recovery / write-off | Dr Cash, or Dr Fraud Loss, / Cr the receivable |
| Any correction | A reversing entry plus a replacement entry. Never an edit |

## 13. Demo (about 3:00)
| t | Action | Show |
|---|---|---|
| 0:00 | — | "Your books can balance while the money goes to the wrong person." |
| 0:10 | **Run Operations** | The operator processes invoices, gets approval for the $40k contractor invoice, pays others, posts the ledger, and reconciles. Everything is green. |
| 0:35 | **Search** | The engine explores N sequences up to depth 4 (live counter) and finds a violation. Minimal counterexample, 3 steps: approve → bank change → batch. Every step is individually valid; the ledger balances. Exposure: $40,000. |
| 1:00 | **Diagnose** | The authorization chain is shown with the broken link highlighted: *"executed payee ≠ approved payee; nothing binds execution to the approval."* |
| 1:20 | **Synthesize** | CEGIS live. Candidate T2 → the search finds a counterexample (change before approval) → refine → T1 + T2 → no violation within k, 0 legitimate payments blocked, 3 holds. Objective scores are shown. |
| 2:00 | **Approve** | Evidence pack and policy diff; a human signs off. |
| 2:10 | **Replay** | Same counterexample → held. Re-search → clean. Deepfake confirmation variant → still held. Legitimate ops green. Before and after side by side. |
| 2:35 | **Fault injection** (precomputed + replayed live) | `drop_ack` → retry → **double payment**. Synthesized T3 → idempotent execution → clean. "Jepsen for financial agents." |
| 2:55 | — | "Break it. Fix it. Prove it." |
| after | **"Try your own scenario"** | A judge describes a threat; it runs live through the same loop (§8.4). A judge can also ask "why did you hold this?" and get a cited explanation (§6). |

**Video:** the brief says to open with the key moment. The video starts with the 3-step counterexample, with every step green and the money gone, then goes back to the operator running normally.

- **Reset demo** takes under 1 second.
- **Judge view** reveals the oracle labels.
- **Playback mode** replays recorded LLM calls offline.
- Phases that hit their timeout fall back to playback.

## 14. UI (war room)
| Area | Contents |
|---|---|
| **Left: Search** | Live sequence counter, violating traces, the minimal counterexample as a step timeline |
| **Center: Twin** | Cash, AP, exposure; invoices, payments, ledger, and bank-feed tabs; the **authorization chain** view for the selected payment (obligation → approval → execution → settlement → books) with coverage marks on each link |
| **Right: Operator + Blue + Approvals** | The Operator's cases; **Blue's verdict feed** (every action: allow / hold / escalate, with evidence); the approvals inbox, including policy patches |
| **Bottom: Synthesis** | The CEGIS iteration log (candidate → counterexample or pass); a scored candidate table; policy diff; before and after |

## 15. Persistence and API
**Postgres / SQLite tables** (via `DATABASE_URL`):

| Table | Contents |
|---|---|
| `runs` | id, kind, parent, profile, policy, scenario, seed, summary |
| `events` | append-only |
| `policies` | rules, diff, approval |
| `searches` | id, policy, alphabet, depth, explored, violations, minimal_trace, duration_ms |
| `syntheses` | gap, iterations JSONB, candidates JSONB, chosen, scores |
| `evidence_packs` | id, synthesis, contents JSONB |
| `llm_calls` | request, response, cache key |

- The engine runs in memory, and events are batch-inserted.
- Supabase: RLS enabled with no policies; a trigger that rejects UPDATE and DELETE on `events`; connection through the session pooler.
- Live updates use SSE from FastAPI.

**API**
```
POST /demo/reset {profile}          POST /runs/{id}/operate
POST /search {run, policy, scenario, depth}        → search id (streams progress)
POST /diagnose {search_id}          POST /synthesize {search_id}  (streams CEGIS)
POST /verify {synthesis_id}         → evidence pack
GET  /approvals · POST /approvals/{id}/decide       POST /policies/{id}/apply
POST /replay {trace, policy}        GET /compare?a=&b=
GET  /runs/{id}/state | /ledger | /chain/{payment}   GET /runs/{id}/events (SSE)
GET  /explain/{entity_type}/{id}                     → cited explanation (§6)
POST /runs/{id}/inject {events | description}        → user-authored threat (§8.4)
GET  /metrics?policies=v0,v1                         → scorecard (§10.1)
```

## 16. Repo layout
```
backend/app/
  main.py  db.py  schemas.py
  twin/{entities,reducer,clock,bank,ledger,gate,facts,profile}.py
  operator/{interface,reference}.py
  guard/{gate,chain,explain}.py
  search/{alphabet,bfs,por,minimize,red}.py
  synth/{coverage,templates,lint,cegis,objective}.py
  verify/{invariants,replay,regression,evidence}.py
  profiles/bayline.yaml
backend/tests/   frontend/   docs/
```

## 17. Build plan (team of 4, now → Sunday 8:30 AM)

### 17.1 Owners
| Owner | Area | Modules |
|---|---|---|
| **P1: Twin** | entities, reducer, clock, bank sim + faults, ledger, gate, v0, invariants, seed + messy data, persistence | `twin/`, `verify/invariants`, `profiles/` |
| **P2: Search + synthesis** | alphabet, BFS/POR/minimize, coverage analysis, templates, lints, CEGIS, objective | `search/`, `synth/` |
| **P3: Operator + Blue explain** | Operator intake (messy formats), exceptions, recovery, approvals behavior, cited explanations, Red content and plain-language inject | `operator/`, `search/red`, `/explain`, `/inject` |
| **P4: Product surface** | war-room UI, SSE, approvals inbox, authorization-chain view, CEGIS log, scorecard, inject form, Reset/playback, video + Devpost | `frontend/`, `verify/evidence`, `/metrics` |

Until M1 lands, P2 and P4 work against P1's entity schemas plus a stub reducer. Freeze the schemas by Sat 2 AM.

### 17.2 Milestones
| Milestone | Contents | Target |
|---|---|---|
| **M1: Twin + gap** | Scenario A violates INV-2/4 from a hand-written trace; hand-installed T1 + T2 fix it; deterministic replay; tests | Sat 12 PM |
| **M2: Search + coverage** | Search finds A's minimal counterexample unaided; coverage diagnosis; **throughput measured**. Operator intake on messy docs. UI shows the run and chain | Sat 4 PM |
| **M3: Synthesis + verify** | CEGIS with LLM plus param sweep, verification suite, evidence pack, approval with SoD. `/explain` with citations. Scorecard v0 vs v1 | Sat 9 PM |
| **M4: Full loop in the UI** | All of the above in the war room, plus Reset, playback, and the inject form (plain language + compose) | Sun 1 AM |
| **M5: Fault + money-in scenarios** | Scenario B (T3) and Scenario F (T6); cash application is in the seed from M1. If time allows: C, D, and approver delays and escalation | Sun 3 AM |
| **Ship** | Sleep, then rehearse ×3 (including one judge-style scenario), record the video (opening on the key moment), Devpost, checklist | Sun 8:30 AM |

**Cut order:** E → D → slow/denying approver behavior → C → multi-month time beyond the seed history → F → live re-search in the demo (use precomputed results) → B. **Never cut:** M1, M2 (real search), M3 (real CEGIS), segregation of duties, cited explanations, user-authored threats, scorecard, the authorization-chain view, before and after.

## 18. What we can and can't claim
| ✅ Can claim | ❌ Can't claim |
|---|---|
| "No violating sequence of length ≤ k within the modeled actions and capabilities" | "Mathematically proven safe" |
| "The root cause is computed from the authorization chain" | "Finds every possible failure" |
| "The control was verified by replay, re-search, held-out variants, and regression" | "Works on your real systems today" |
| "Exposure" | "Losses prevented" |
| "Synthesizes controls from a bounded template library" | "Rewrites arbitrary financial software" |

## 19. Risks
| Risk | Mitigation |
|---|---|
| The search is too slow | Measure at M2; state-hash deduplication and partial-order reduction; drop to depth 3; parallel workers; precompute for the demo |
| CEGIS doesn't converge | An enumerative parameter sweep backs up the LLM; 4-iteration cap; honest "cannot auto-repair" |
| It looks scripted | Live search counter, a real rejected candidate, Judge view, judge-editable parameters |
| The track reads as "security tool" | The demo opens with the operator running finance; the pitch centers on autonomous ops that are trustworthy |
| Scope | The cut order above; one core scenario done fully beats five done partially |
| Network or API trouble | In-memory engine, SQLite fallback, playback, backup video |

## 20. Submission checklist
- [ ] **Code is submitted and judges can open it.** The track requires code, and the repo is currently **private**. Make it public or add the judges before 9 AM.
- [ ] No secrets in git history.
- [ ] README with a one-command run, playback mode, and the real-vs-simulated table (§10.2).
- [ ] The video **opens with the key moment** and fits Devpost's length limit.
- [ ] Devpost entry on the Hyphenate track, including:
  - the seats line (§1);
  - the Red / Blue / Operator split (§1.2);
  - real vs simulated;
  - the scorecard.
- [ ] A full demo run works after Reset, both live and in playback. The inject flow works live with a scenario we've never run before.

## 21. Config
`backend/.env` (you type secrets in yourself; never commit it):
```
DATABASE_URL=postgresql+psycopg://...   # Supabase session pooler; or sqlite:///./vandal.db
ANTHROPIC_API_KEY=...
MODEL_AGENT=claude-sonnet-5-5
MODEL_SYNTH=claude-opus-5-5
SEARCH_DEPTH=4
SEARCH_WORKERS=8
DEMO_PLAYBACK=false
```

## 22. Open questions
1. ~~**Team size.**~~ Resolved: 4 people. Owners are in §17.1; names still need to go against P1–P4.
2. **Hosted demo, or laptop?**
3. **Anthropic credits.** Use Opus for synthesis, or Sonnet only?
4. **Fault injection in the live demo.** Run Scenario B live, or precompute it and replay?
5. **Interactive judges.** Let a judge pick the search depth, or toggle an attacker capability (e.g. allow portal takeover) and watch the synthesized control change?
