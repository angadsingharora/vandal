# Vandal — Plan Review

Review of the project brief ([SPEC.md](SPEC.md)) before writing the design doc ([DESIGN.md](DESIGN.md)).
Written 2026-10-23, roughly 36 hours before the 9:00 AM PT Sunday submission deadline.

## Verdict

The plan is good and worth building. The closed loop of break, diagnose, repair, and replay is a strong demo. The brief already makes the right calls on the hard parts: a deterministic ledger separate from the models, append-only corrections, replay from a snapshot, and "one real loop beats many fake features."

Six changes would make it much more likely to win and to actually work by Sunday morning. They are listed below in priority order. DESIGN.md already includes all of them.

## What the plan gets right

- **Fit with Hyphenate.** Hyphenate's platform covers procure-to-pay, treasury reconciliation, and GL work, and it promises outputs that are "deterministic, explainable, auditable." Its blog defines autonomy as *doing* the work, knowing when to escalate, and remembering the answer. Vandal's repair engine is that "remember the answer" step, made provable. Use that line in the pitch.
- **Deterministic verification separate from the LLM.** This is the single most important technical decision, and it is already in the brief.
- **Append-only corrections.** Reversing entries are used instead of overwrites, and a payment that already went out leads to a recovery workflow. Finance judges will notice this.
- **A disciplined MVP.** The plan has one scenario end to end, a clear list of what not to build, and metrics that come only from real runs.

## Issues and recommended changes

### 1. Lead with the finance operator, not the attacker (pitch and positioning)

The challenge asks for "an autonomous system a finance team would hire." The three-minute pitch in §12 opens on adversarial testing, which makes it sound like a security tool. Reframe it:

> *An autonomous AP operator that hardens itself. Every time something gets past it, it finds the missing control, installs it, and proves the fix by replaying the attack.*

Red Agent is the test harness that drives that loop. There are two customer stories, and you can tell both:

- A finance team hires the self-hardening AP operator.
- AI-finance vendors (companies like Hyphenate itself) use Vandal as their release gate.

Say the second one to Hyphenate's judges directly.

### 2. A "deliberately vulnerable baseline" will look staged unless the vulnerability is realistic

If the baseline obviously has a hole planted in it, judges will discount the whole demo. To avoid that:

- Make the baseline controls **realistic defaults**: 3-way match (PO, receipt, invoice), approval required above $25,000, and a vendor-active check. The $15,000 bank-change attack slips under the approval threshold, so the baseline is a normal mid-market setup with no planted hole.
- Show Red's **failed attempts** before the one that succeeds. An attacker that wins on its first try looks scripted.
- Let a judge **change the attack parameters** live (amount, channel, timing).

### 3. If the LLM handles every invoice, the baseline may not fail, or may not fail reliably (demo risk)

If Blue's LLM reads every invoice, it may notice the bank change on its own. Then the baseline attack fails and there is nothing to repair, or it fails only some of the time. **Recommendation:** use the architecture real AP automation uses, which is also Hyphenate's "steps in only where it matters":

- **Straight-through processing.** Invoices that pass the policy engine are paid by deterministic code. No LLM is involved.
- **Exception handling.** Only invoices that a policy flags go to Blue's LLM. Blue investigates, holds, escalates, drafts the vendor callback, and runs recovery.

That makes the baseline failure deterministic, and replay outcomes depend on the enforced control rather than on the model's mood. It is also more honest: the LLM does judgment work, and code does the gating.

### 4. Bound the repair space with a policy DSL over a fixed fact catalog (repair has to really work)

"Propose a precise policy change" needs a concrete, machine-checkable target. Use JSON rules of the form `when <predicate over facts> then hold | escalate | block`, where:

- the facts come from a fixed catalog of deterministic fact providers, such as `vendor.bank_account.days_since_change` and `invoice.duplicate_candidates.count`;
- the LLM only **composes facts into a rule**, and the validator checks it against a schema, replays the attack, and runs the legitimate regression suite.

If a fix needs a fact that doesn't exist, the engine reports "cannot auto-repair, escalate." That is an honest answer, and a credible one.

### 5. Define "failure" with a hidden oracle, not with the agents' judgment (correctness)

Some invariants can be checked from state alone: "every journal entry balances" and "an invoice is not paid twice." The bank-change case cannot. Nothing in the visible state says the new account belongs to an attacker. So scenarios write **oracle labels** (for example, `bank_account X is attacker-controlled`) to a table that no agent tool can read. The verification engine checks those labels and the agents never see them. This keeps the "proof" honest, and it is a good technical-depth point to show judges.

### 6. Replay the recorded attack, don't regenerate it (determinism)

Replay must re-run **Red's recorded actions** from the same seed snapshot. Asking the LLM again would produce a different attack, and the before-and-after comparison would mean nothing. The regression suite is the same list of legitimate invoices each time.

## Smaller notes

- **"Mathematically verifies" overclaims.** Say "verified by replay against financial invariants." Avoid "proof" in the formal sense, because a finance judge will push back on it.
- **Metrics from a handful of runs look thin.** Generate about 40 attack variants and about 80 legitimate invoices, then run the batch against policy v0 and v1. That gives real before-and-after attack-success and false-positive rates in one table.
- **Adaptive Red is cheap if it's scoped.** After a repair, Red tries variants to get around the new rule. For example, an exact-match duplicate check is beaten by `INV-1042-A`, which triggers a second repair to fuzzy matching on vendor, amount, and date window. If time allows, this is the best "wow" moment after the main loop.
- **The reconciliation scenario has a different shape.** It shows off Blue's skill at classifying discrepancies; it isn't an attack-repair loop. Make it a stretch goal.
- **Typo:** "Reconciliating" in §1 should be "Reconciling."
- **React Flow is decoration.** A timeline and a policy diff carry the story. Cut React Flow if time runs short.

## Supabase

**Update (resolved):** the connector was re-authorized and now reaches project `cduqfuzdkwkjobiqmgqs` in the "vandal" org (Postgres 17, us-east-1, empty `public` schema).

Originally, the Supabase connector in this session was signed in to an account with **no projects**. Project `cduqfuzdkwkjobiqmgqs` belongs to a different Supabase account or organization, so I couldn't connect to it. To fix this, do one of these:

- Reconnect the Supabase connector while signed in to the account that owns the project.
- Put the project's Postgres connection string in `backend/.env` as `DATABASE_URL`. Copy it from the Supabase dashboard (Connect → Session pooler). Type it in yourself; don't paste it into chat.

Design consequence: replays reset state over and over, and venue Wi-Fi is unreliable. So the backend talks to the database through SQLAlchemy using `DATABASE_URL`: Supabase Postgres for the hosted demo, with a SQLite fallback for running offline. Every row is scoped by `run_id`, so snapshot and reset never require dropping tables.

## Open questions for you

1. **Team size and split.** Who is on frontend, backend or simulation, and agents? DESIGN.md §14 assumes 2–4 people.
2. **Hosting.** Will you run the demo from a laptop on stage, or deploy it (frontend on Vercel, backend on Fly or Railway)?
3. **Anthropic API credits.** Do you have them? This decides which models to use. The default is Sonnet for the Red and Blue loops and Opus for diagnosis and repair.
