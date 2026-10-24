# VANDAL

**Break it. Fix it. Prove it.**

> Original product brief, as provided by the team. See [PLAN_REVIEW.md](PLAN_REVIEW.md) for the review and [DESIGN.md](DESIGN.md) for the design.

## 1. Project overview

We are building Vandal, an adversarial testing and autonomous repair platform for AI-powered financial systems.

The idea is simple: as companies increasingly give AI agents responsibility for managing financial operations, how can they know those agents won't make costly mistakes?

Vandal creates a realistic simulated company with bank accounts, vendors, invoices, payments, accounting records, and financial policies. It then introduces adversarial AI agents whose job is to discover ways the company's financial workflows could fail.

When an attack succeeds, a defensive finance agent investigates the failure, identifies the underlying weakness, repairs the affected workflow or financial controls, and replays the attack to verify that the fix works.

Vandal doesn't just find financial failures. It attempts to fix them and mathematically verifies whether the system is now safer.

The ultimate vision is to become the reliability infrastructure for autonomous finance, allowing companies to stress-test and validate their financial AI systems before deploying them with real money.

## 2. The situation: Cal Hacks 13.0

We are participating in Cal Hacks 13.0, taking place October 23–25, 2026, at the Palace of Fine Arts in San Francisco.

We are specifically targeting Hyphenate's sponsored challenge.

### Hyphenate track details

Official challenge: The Hyphenated Enterprise: Autonomous Systems for Finance

Prizes:

- First place: $8,000
- Second place: $5,000
- Third place: $3,000
- Top five teams: Expedited interview opportunities with Hyphenate

Submission deadline: Sunday, October 25, at 9:00 AM Pacific.

Official competition: https://cal-hacks-13-0.devpost.com/

Hyphenate's organizer-provided challenge description asks participants to build an autonomous system that a finance team would hire, for a company of their choosing.

Hyphenate is an autonomous finance company that builds AI agents capable of performing actual financial operations. Its software works across accounts payable, receivables, treasury, accounting, reconciliation, and financial reporting.

The company's philosophy is that AI should not merely flag problems or generate suggestions. It should actually execute financial workflows, handle exceptions, document its decisions, and know when human judgment is required.

Relevant background:

- https://hyphenate.ai/
- https://hyphenate.ai/platform
- https://hyphenate.ai/blog/what-we-mean-by-autonomous-finance

### Why Vandal fits Hyphenate

Vandal must demonstrate more than security testing.

The central part of the project is an autonomous financial system capable of:

- Processing and validating invoices
- Maintaining consistent accounting records
- Investigating suspicious transactions
- Reconciliating financial inconsistencies
- Preventing unauthorized payments
- Preparing or executing permissible financial corrections
- Repairing weaknesses in financial workflows
- Maintaining an auditable history of its actions

The attacking AI agents are used to test those autonomous finance capabilities.

The finance operator and recovery system should be the core of our Hyphenate submission. The attacks are how we demonstrate that its autonomy works under pressure.

The challenge organizers have not explicitly stated that adversarial testing is a separate scoring requirement. We are pursuing this interpretation because autonomous exception handling and repair directly support the theme.

### General Cal Hacks judging criteria

The organizers list five criteria:

1. Application: Is there a meaningful real-world use case and identifiable customer?
2. Intentionality: Does the product have a clear purpose and intuitive user experience?
3. Functionality: Does the working demo actually do what it claims?
4. Creativity: Does it combine ideas or solve problems in an original way?
5. Technical complexity: Does the implementation demonstrate substantial engineering depth?

We want to score strongly on all five.

This is a weekend hackathon. The project does not have to be production-ready. It does need to show a genuinely working technical system rather than a scripted dashboard.

## 3. The core product

Vandal is a financial crash-testing environment.

Imagine a company using AI to manage payments and accounting.

Its autonomous finance agent has access to:

- Vendor records
- Purchase orders
- Invoices
- Bank account information
- Payment approvals
- A general ledger
- Transaction histories
- Financial policies

Everything runs in an isolated simulated environment. No real banking credentials, money, or customer records are necessary.

We then introduce two primary actors.

### RED AGENT — The attacker

Red Agent's objective is to find ways the simulated financial system can produce incorrect financial outcomes.

It should operate through controlled test inputs and predefined sandbox capabilities, such as:

- Introducing an altered vendor record
- Submitting a duplicate invoice
- Supplying inconsistent purchase-order information
- Creating conflicting payment instructions
- Introducing delayed or contradictory transaction records

Red Agent should actively look for weak points in how the finance operator interprets information, verifies financial instructions, and processes transactions.

It should ideally adapt its next test based on previous outcomes, rather than run only static scenarios.

All activity must remain within our authorized simulated environment.

### BLUE AGENT — The autonomous finance operator

Blue Agent runs financial operations and responds to inconsistencies.

Its responsibilities are to:

- Process legitimate invoices
- Validate financial records against available evidence
- Apply company policies
- Decide whether transactions are ready to execute
- Investigate unusual discrepancies
- Hold suspicious or unsupported transactions
- Prepare or apply safe financial corrections
- Escalate uncertain decisions
- Explain its actions and maintain an audit trail

This must be a genuinely functioning finance agent with tools that can change sandbox state.

### REPAIR ENGINE — The self-healing layer

This is arguably our most important differentiator.

When the system experiences a failure, the repair process should:

1. Reconstruct what happened.
2. Identify the violated financial invariant or missing control.
3. Determine the underlying cause.
4. Propose a precise policy, configuration, or workflow change.
5. Validate the proposed change.
6. Apply the approved fix inside the sandbox.
7. Replay the original attack from a clean state.
8. Run legitimate transactions as regression tests.
9. Report whether the failure is genuinely fixed.

For the hackathon, automatically modifying a structured financial control is sufficient. We do not need an unrestricted AI rewriting arbitrary production code.

An example would be installing a rule requiring independent verification before a vendor's bank details can be changed.

Vandal should prove a failure existed, apply a real correction, and show that the same failure no longer occurs.

## 4. Concrete hackathon scenario

To keep the project grounded, start with a fictional midmarket property-management company.

It manages numerous properties and routinely pays plumbers, electricians, maintenance companies, security contractors, and other vendors.

Our simulated business might have:

- $2 million across fictional bank accounts
- 25 vendors
- 80 invoices
- Multiple properties and expense categories
- A general ledger
- Payment approval rules
- A history of completed transactions

These figures are illustrative and can be adjusted to fit the implementation.

### Why property management?

It gives us realistic financial complexity without requiring specialized banking knowledge. Contractors submit invoices, payment details can change, and expenses need to be correctly allocated to properties. It provides an understandable environment for the judges.

However, property management is only the initial testing environment, not the long-term limit of the company.

### Primary demo attack: Vendor account manipulation

A legitimate contractor is owed $15,000.

An adversarial test introduces conflicting bank details into the simulated vendor-payment workflow.

In an intentionally vulnerable baseline configuration, the finance agent fails to verify the change and authorizes an incorrect sandbox payment.

Vandal must then:

1. Detect the discrepancy between established vendor records and the new payment information.
2. Trace which record or control caused the incorrect action.
3. Identify the missing verification requirement.
4. Apply an enforceable policy fix.
5. Reset the simulation to a clean snapshot.
6. Replay the same attack.
7. Verify that the unauthorized payment is now blocked.
8. Confirm that legitimate contractor payments still proceed normally.

We should make the before-and-after behavior obvious.

### Secondary scenario: Duplicate payments

Red Agent introduces a duplicate of an existing vendor invoice.

The finance operator should identify the duplication by comparing available invoice identifiers, vendor information, purchase orders, and historical payments.

If the original workflow incorrectly permits duplicate payment, Vandal should generate and validate an idempotency or duplicate-detection control.

The retest must demonstrate that the same invoice cannot be paid twice.

### Third scenario: Broken reconciliation

Simulate an accounting mismatch involving a bank-feed event arriving late or an incorrectly classified ledger entry.

Blue Agent must identify whether the discrepancy represents missing information, an incorrect posting, or simply an unsettled transaction.

It should prepare the appropriate accounting action, apply permitted corrections, and generate an auditable reconciliation.

The system must not invent a transaction merely to make two balances match.

## 5. The killer live demo

We want Vandal to look like an interactive financial testing terminal or war room, not a conventional SaaS admin dashboard.

### Phase 1 — Everything works

Show the fictional company's finances.

The AI finance operator processes several valid invoices, prepares payments, and updates the general ledger.

The judges see that this is a working financial system before any attacks begin.

### Phase 2 — Unleash Vandal

A user initiates an adversarial test run.

Red Agent introduces a financial inconsistency.

We observe how the finance agent processes it. In the intentionally vulnerable baseline, the financial system makes an incorrect decision.

The UI should clearly show the actual state transition and financial exposure.

### Phase 3 — Diagnose

Vandal identifies the failed operation and reconstructs its cause using transaction records, policies, and tool execution logs.

It should explain the issue in plain language.

For example:

"The system accepted a vendor bank-account change without independent verification. This allowed payment authorization against unverified instructions."

### Phase 4 — Repair

Vandal generates a financial-control patch.

The patch is validated and applied to the simulated workflow.

The product should show the actual difference in the policy or execution logic.

### Phase 5 — Run it back

Replay the original test using the repaired financial system.

The malicious transaction is now rejected, legitimate transactions still succeed, and the financial records remain consistent.

This is the defining moment of our project.

The demo should communicate:

We deliberately broke an autonomous finance system, showed exactly how it failed, repaired the control, and demonstrated that the same failure no longer works.

Aim for a live demonstration that can be explained in approximately three minutes, with a recorded backup.

## 6. Technical architecture

Prioritize a Python backend because we want to implement financial simulation, agent orchestration, and verification quickly.

### Suggested stack

**Frontend**

- React / Next.js
- Tailwind CSS
- React Flow or another graph component for financial workflows
- Live event timeline
- Transaction and ledger views
- Before-and-after comparison

**Backend**

- Python
- FastAPI
- SQLite initially, PostgreSQL if necessary
- Pydantic for structured data validation
- Agent orchestration using an appropriate SDK or lightweight custom framework

**AI**

- Use an available LLM API for Red Agent and Blue Agent reasoning.
- Require structured outputs for proposed actions.
- Do not trust model-generated financial calculations without validation.
- Keep models separate from the deterministic ledger and authorization mechanisms.

**Financial simulation**

- Event-driven transaction engine
- Double-entry accounting
- Invoice and payment state machines
- Reproducible database snapshots
- Configurable financial-control rules
- Deterministic test and replay engine

### Suggested main components

**1. Sandbox Environment**

Holds the simulated company's financial state.

Suggested entities include:

- Company
- Vendor
- VendorBankAccount
- PurchaseOrder
- Invoice
- Payment
- BankTransaction
- LedgerAccount
- JournalEntry
- Policy
- Approval
- AuditEvent

**2. Finance Agent Runtime**

Exposes authorized finance tools such as:

- `get_invoice`
- `get_vendor_history`
- `match_purchase_order`
- `verify_vendor_account`
- `review_payment`
- `hold_payment`
- `execute_simulated_payment`
- `get_bank_transactions`
- `reconcile_account`
- `prepare_journal_entry`
- `post_validated_journal_entry`

Every tool must enforce permissions and validate its inputs.

**3. Adversarial Scenario Generator**

Generates controlled test cases against the simulated environment.

An attack scenario should specify:

- Starting financial state
- Adversarial objective
- Permitted test actions
- Modified input or event
- Target workflow
- Expected financial invariants
- Success or failure criteria

**4. Financial Verification Engine**

Independently checks whether the resulting financial state is valid.

Important invariants include:

- Every posted journal entry balances.
- Payments cannot exceed authorized amounts.
- A payable cannot be settled twice.
- Vendor payment instructions require the appropriate verification.
- Invoice and payment records must remain reconcilable.
- Unsettled payments must be distinguished from completed payments.
- All corrections preserve historical audit records.
- Uncertain or high-risk financial decisions require approval.

**5. Repair and Replay Engine**

Receives failures, proposes narrowly scoped changes, validates them, and replays relevant scenarios.

The replay must use a consistent starting snapshot so the before-and-after comparison is meaningful.

A patch is only considered successful when the original failure no longer occurs and relevant legitimate financial operations still work.

### Important implementation principles

Do not build this as agents freely editing database rows.

Financial state changes need to flow through validated operations and immutable or append-only audit records.

For example, a posted journal entry should generally be corrected through a new reversing or adjusting entry, not silently overwritten.

If a simulated payment has already completed, applying a new rule does not retroactively undo the transaction. That situation should produce an appropriate recovery or correction workflow.

This distinction matters if we want the product to be credible to financial software companies.

## 7. The actual MVP for this weekend

We do not need a complete autonomous-finance operating system.

### Must have

**A functioning miniature finance environment**

- Seeded vendors, invoices, purchase orders, and account balances
- Legitimate invoice-processing workflow
- Simulated payments
- Consistent double-entry ledger

**An adversarial agent**

- Able to select or generate controlled financial failure scenarios
- Able to submit those scenarios to the sandbox
- Logs its actions and outcomes

**A defensive finance agent**

- Investigates inconsistencies
- Uses real financial tools
- Holds or processes payments
- Produces appropriate finance records

**One real self-healing demonstration**

- One attack succeeds against the vulnerable baseline
- Vandal investigates the problem
- A structured repair is generated and applied
- Replay proves the original failure is blocked
- Legitimate transactions still pass

**A presentable interface**

- Visible company financial state
- Red and Blue agent activity
- Transaction execution timeline
- Financial exposure
- Diagnosis
- Repair
- Before/after testing results

### Nice to have

- Three different attack scenarios
- Multiple autonomous attackers
- Adaptive attacks following an unsuccessful attempt
- Auto-generated regression test cases
- Multiple simulated company profiles
- Financial reliability scoring
- Downloadable audit and evaluation reports

### Do not prioritize

- Real bank connections
- Real payments
- Live financial account credentials
- A complete ERP
- A general-purpose accounting product
- Autonomous deployment of arbitrary AI-generated code changes
- Sophisticated ML models where deterministic financial rules are more reliable

One genuine, impressive closed-loop demo is substantially more valuable than a large number of unfinished features.

## 8. Measuring whether Vandal works

Avoid showing metrics that are not produced by actual tests.

Useful metrics include:

- **Attack success rate:** Percentage of controlled adversarial scenarios that caused a defined financial failure.
- **Financial exposure:** Amount of simulated money involved in vulnerable transactions.
- **Detection rate:** Percentage of injected issues correctly identified.
- **Repair success rate:** Percentage of reproducible failures that no longer occur after validated changes.
- **False-positive rate:** Percentage of legitimate financial transactions incorrectly blocked.
- **Recovery time:** Time required to investigate and correct a simulated financial inconsistency.

A strong result would show that an attack succeeds before a repair, fails afterward, and normal transactions remain operational.

Do not equate financial exposure with actual money lost.

## 9. Interface and branding

Product name: VANDAL

Tagline: Break it. Fix it. Prove it.

Alternative pitch line: Break financial AI before it breaks your business.

The UI should feel like an engineering control room for financial infrastructure.

Suggested experience:

- Dark, technical visual design
- One side showing adversarial tests
- One side showing the autonomous finance operator
- A central view of financial state and transaction flow
- Live, timestamped events
- Clear severity and payment-status indicators
- Visible patches and replay results

Prioritize meaningful interactions over decorative animations.

The central action could be called Run Attack, Stress Test, or Unleash Vandal.

After a failure is found, the most important action is Repair & Replay.

The experience should be memorable while still feeling like software an enterprise financial engineering team could eventually purchase.

## 10. Long-term startup vision

### What company are we trying to build?

Vandal could become a financial reliability engineering platform for autonomous AI.

As AI agents take responsibility for accounting, payments, treasury, reconciliation, and other high-stakes financial workflows, businesses will need confidence that these systems work correctly under unusual conditions.

Traditional software testing is important but not sufficient for every behavior of an agent that interprets documents, makes decisions, and uses state-changing tools.

Vandal would let companies test those systems against financial-specific failure scenarios, measure the consequences, deploy validated control changes, and continuously verify that future releases remain reliable.

### Initial customer

Our first target customers would be software companies building AI-powered accounts-payable or accounting agents.

Their engineering and risk teams could use Vandal to test new agent releases before customers trust those systems with financial operations.

We are not initially trying to sell to every property manager or every small business.

The property-management environment is an example test fixture. The commercial customer would be the company building the financial automation software.

### Future expansion

Eventually, Vandal could support:

- Accounts-payable agents
- Accounts-receivable agents
- Autonomous treasury systems
- Banking and payment agents
- Insurance claims automation
- Enterprise accounting systems
- AI-controlled financial workflows across multiple software providers

### Business model

A plausible business model is enterprise SaaS sold to financial software engineering teams.

Potential pricing factors:

- Number of finance agents tested
- Number of adversarial test executions
- Financial workflow complexity
- Continuous integration and regression testing
- Advanced remediation capabilities
- Compliance and audit reporting

These are hypotheses, not validated pricing.

### What makes the startup defensible?

The moat should not just be having a Red Agent and a Blue Agent.

Generic AI-agent red-teaming platforms already exist.

Relevant adjacent companies include Pensar and Straiker. Financial-agent safety benchmarks such as FinVault also demonstrate that realistic, stateful financial-agent testing is an active research area.

Potential differentiation comes from:

1. **Financial-state verification:** Understanding whether accounting records and money movements are genuinely correct, not just whether a model produced a suspicious response.
2. **Autonomous remediation:** Proposing and applying validated financial-control fixes.
3. **Reproducible replay:** Proving that repaired systems behave differently under the same conditions.
4. **Finance-specific environments:** Realistic AP, treasury, and accounting workflows instead of generic chatbot tests.
5. **Continuous evaluation:** Eventually becoming part of the deployment process for financial agents.

An eventual product might plug into a company's testing environment, run financial adversarial scenarios whenever a finance-agent release changes, and block a release when critical financial invariants fail.

### Biggest venture risks

- Existing AI-security companies could expand into finance-specific testing.
- Financial software vendors may prefer internal testing.
- Reproducing production financial workflows safely could be difficult.
- Automated remediation is substantially harder than generating failure reports.
- Enterprise buyers will require evidence that Vandal reduces actual risk.

These are reasons to validate the product after the hackathon, not reasons to avoid building a prototype.

We should not claim this category is completely new.

## 11. Why the idea is compelling

Most cybersecurity demonstrations focus on getting an AI to produce a malicious response or perform an unauthorized tool call.

Vandal focuses on the financial consequences.

The questions are:

- Can an AI accidentally pay the wrong vendor?
- Can inconsistent records lead to a duplicate payment?
- Can it corrupt the ledger while believing reconciliation succeeded?
- Does it detect when financial evidence is unreliable?
- Can it recover without introducing new financial errors?
- Can it repair the underlying workflow rather than just reject one transaction?
- Can we prove the repair actually works?

This is the distinction between testing an AI model and testing an autonomous financial system.

That is the core idea behind Vandal.

## 12. Our three-minute pitch

"Companies are starting to trust AI agents with their financial operations. They're letting agents pay vendors, manage invoices, and reconcile their books.

But how do you know an autonomous finance agent won't make a $100,000 mistake?

We built Vandal.

Vandal creates a realistic financial environment and deploys adversarial AI agents to find ways the system can fail.

When something breaks, our defensive finance agent investigates exactly what went wrong, repairs the affected financial control, and reruns the same attack to verify that the fix works.

We're not just detecting vulnerabilities. We're testing whether autonomous financial systems can recover from them and proving that the underlying problem has been resolved.

Today, Vandal is a financial crash-testing sandbox. Our larger vision is to make it the reliability infrastructure companies use before trusting AI with real money."

## 13. How the engineering agent should approach implementation

Do not attempt to implement every idea in this document.

Treat this as the complete product vision and requirements context.

Work backward from one successful live demonstration:

1. Build a functioning miniature finance system.
2. Implement a legitimate payment workflow.
3. Introduce a reproducible financial failure.
4. Use an AI agent to investigate and identify the problem.
5. Generate and apply an enforceable policy repair.
6. Replay the original scenario.
7. Prove that the failure no longer occurs.
8. Validate that legitimate payments continue to work.
9. Surface all of this in a clean interface.

Prioritize architecture that makes the repair and replay genuinely work.

The product should not depend on prewritten explanations or hardcoded outcome screens to appear autonomous. Deterministic financial rules, structured agent actions, and real state transitions matter more than fancy prompts.

If time becomes constrained, sacrifice secondary attack scenarios and decorative UI before sacrificing the main repair-and-replay workflow.

The non-negotiable end state:

A judge watches an autonomous finance system fail under a controlled attack. Vandal diagnoses the failure, applies a real fix, and reruns the attack. The attack fails the second time, the legitimate finance workflow still works, and the system produces evidence explaining why.

That is the hackathon product.

The venture is everything that happens when companies want to run that same process across thousands of financial-agent deployments.
