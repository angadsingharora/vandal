# Vandal — Devpost entry (Hyphenate track)

**Break it. Fix it. Prove it.** A red team and a blue team for AI that runs a company's money.

## Inspiration

Your books can balance perfectly while the money goes to the wrong person. Finance agents now execute payments, and attackers now have deepfakes and malicious agents. Controls designed for human clerks have gaps an agent walks straight through, such as reading the vendor's *current* bank account at payment time. We wanted an autonomous finance operation a controller would actually hire: one where every action is checked before money moves, and where the checks get better by being attacked.

## The seats it fills

At a 12-property real-estate manager, **the Operator** fills the AP specialist (intake, GL coding, payment runs), the vendor-master clerk (bank and contact changes), the treasury and payments analyst (cash position, execution, bank errors), the AR and cash-application clerk (applying payments, refunds), and the staff accountant (reconciliation, corrections, recovery). **Blue** fills the internal-controls reviewer: the person who checks every payment, refund, and vendor change before release and asks "is this allowed, and does it match what was approved?" Both report to the controller, who approves large payments, refunds to new destinations, and every new control.

## What it does: Red, Blue, and the Operator

| | **Red: Vandal Sandbox** | **Blue: Vandal Guard** | **The Operator** |
|---|---|---|---|
| What | A deterministic *financial twin* of the company, plus bounded adversarial search over attacker and fault moves, Red content attacks (deepfake calls, lookalike emails, malicious counterparty agents), control synthesis (CEGIS), and a six-check verification engine | A verification layer in the live path. Every agentic action (pay, change vendor bank details, refund, post an entry) goes through it. Blue checks the authorization chain (obligation → approval → execution → settlement → books), the active controls, and the invariants, then allows, holds, or escalates, records the evidence, and explains any decision with citations | The finance agent doing the work: Claude reads messy invoices (email bodies, OCR'd scans, forwarded threads, line-item tables), codes the GL, asks for approvals, runs payments, reconciles, and recovers misdirected money. Any agent can plug in through the `FinanceOperator` interface |
| When | Offline: before deployment and after every change | Online: on every action, in the sandbox and in the live demo | Always |
| Output | Counterexample → root cause → synthesized control → verification pack | A verdict, the evidence behind it, and an audit trail | The finance work |

Every gap Red finds becomes a control Blue enforces. Fixes go into Blue's controls, never into the model: no retraining, no prompt edits. The Operator can't skip a control, approve its own work, or talk its way past a hold.

## The self-healing loop

1. Red clones the live company and attacks the clone.
2. Search finds a sequence Blue's current controls let through, in which every step is individually valid and the ledger balances. The root cause is computed from the authorization chain.
3. The synthesizer proposes controls from a fixed template library; search attacks each candidate; a candidate that lets an attack through or blocks a legitimate payment is refuted, and the next proposal learns from it.
4. A human approves the control in the inbox (the synthesizer can't approve its own patch; neither can the Operator).
5. The control is installed in Blue. Red replays the attack: held.

## What's real, what's simulated, and how we know

| Real | Simulated | How we know it works |
|---|---|---|
| Double-entry ledger, invariants, policy gate, bounded search, CEGIS verification (deterministic code with tests) | The company, vendors, bank accounts, and money | Hidden oracle labels act as an answer key no agent can read |
| Claude reading every document, proposing controls, and explaining with citations | Callbacks, deepfakes, and counterparty agents, modeled as channel events with forgeable attributes; no synthetic media | Held-out variants the synthesizer never saw, plus a re-search under the new policy |
| The synthesizer proposing controls, and search refuting or accepting them | Bank behavior and faults (timeouts, dropped acks, late feeds) | The scorecard: before-and-after rates from actual runs |
| Replay of any recorded trace | Approvers, when no human is present | Replay-determinism tests |

Models propose; code decides. Search and verification always run the deterministic reference Operator, so money outcomes never depend on a model's mood.

## The scorecard

From an actual run (`GET /metrics`, the war room's Scorecard dialog), v0 against the policy CEGIS synthesized live, `v1-synth` = approval binding + verified account changes:

| | v0 | v1-synth |
|---|---|---|
| Violations found by search | 12 | 0 |
| Attack success rate (40 held-out variants) | 100% | 0% |
| Exposure | $300,787 | $0 |
| Legitimate payments blocked | 0 | 0 |
| False-positive rate | 6.7% | 0.0% |
| Broken invariants in legitimate runs | INV-2, INV-5 | none |
| Intake field accuracy (120 fields, 24 messy documents) | 100% | 100% |
| GL-coding accuracy | 100% | 100% |

Verification of `v1-synth` at depth 3: 34,676 sequences re-searched, no violation; 0 of 40 held-out variants succeeded; 25 of 25 regression cases passed; all 80 seeded invoices paid, 0 holds, 0 blocks. These are bounded claims: no violating sequence of length ≤ k within the modeled moves, verified by replay, re-search, held-out variants, and regression. Not a proof beyond that.

## Demo script (3:00)

| t | Action | What's on screen |
|---|---|---|
| 0:00 | — | "Your books can balance while the money goes to the wrong person." |
| 0:10 | **Run operations** | The Operator processes 80 invoices, gets the controller's approval for the $40k contractor invoice, pays, posts, reconciles. Every tool call shows Blue's verdict. Everything green. |
| 0:35 | **Unleash Vandal** | The live sequence counter; 12 violating traces; the minimal counterexample is **one move**: a lookalike-domain email changing the vendor's bank details after approval, before the batch. Every step valid, ledger balanced. Exposure: **$40,000**. |
| 1:00 | **Replay on twin → Diagnose** | The Attack tab: the payment, the attacker's account (Judge view reveals the answer key). The authorization chain with the execution link broken: *"executed payee ≠ approved payee; nothing binds execution to the approval."* |
| 1:20 | **Synthesize a control** | CEGIS live, with Claude proposing: T2 approval binding → search beats it with a change *before* approval → T2 + T1 verified account change survives; a T1 that accepts video calls is refuted by the spoofable lint. Scores on screen. |
| 2:00 | **Verify → Submit → Approve as Controller → Apply** | Six checks pass; the evidence pack and policy diff go to the inbox; a human signs off. The Operator can't. |
| 2:10 | **Replay under v1-synth** | Same counterexample: **HELD, $0**, every invariant holds. Then "a vendor emails new bank details after approval, then calls to confirm" from the inject form: the deepfake confirmation is held too. |
| 2:35 | **Scenario B** | `drop_ack → retry → double payment`; the synthesized T3 makes execution idempotent. "Jepsen for financial agents." |
| 2:55 | — | "Break it. Fix it. Prove it." |
| after | **Try your own scenario** / **why?** | A judge describes a threat in plain language; Claude maps it onto moves, it runs through the same loop live. Ask Blue why a payment was held and push back: every claim cites an id, and the hold stands. |

## How we built it

Python 3.12, FastAPI, Pydantic; a deterministic twin where every run is `fold(seed, events)` and the same seed and events always give the same state hash; integer cents, a sim clock, no wall-clock time. Breadth-first search with state-hash deduplication and partial-order reduction over a discretized attacker alphabet; delta-debugging minimization; a CEGIS loop over six control templates with overfit, spoofability, and block-where-hold-works lints. Claude (Sonnet for the Operator and Blue's explanations, Opus for synthesis) through one wrapper with structured output and a content-keyed cache, so the whole demo replays offline. Next.js war room with live SSE. Playback, mock fixtures, and a smoke script that drives the entire loop over the API.

## What's next

Sources that disagree (invoices above the contracted rate, feed lines net of wire fees), Scenario D (split and duplicate invoices, T4/T5), and plugging a customer's own finance agent into the `FinanceOperator` seat.
