# Vandal: Devpost entry (Hyphenate track)

Each section below matches a field on the Devpost submission form. Paste them in order.

---

## Name

Vandal

## Elevator pitch

_(Devpost limit: 200 characters.)_

> Security for AI that runs a company's money. Vandal Strike attacks a twin of your finances, writes the fix, and proves it. Vandal Guard enforces it on every live payment.

---

## About the project

### Inspiration

**Your books can balance perfectly while the money goes to the wrong person.**

Finance agents now pay vendors, change bank details, and issue refunds without a human touching each step. Attackers now have lookalike domains, cloned voices, and malicious counterparty agents. The controls companies rely on were designed for human clerks, and an agent walks straight through their gaps.

Here's the classic one. An invoice is approved. Before the payment batch runs, an email from `acme-roofing.co` (not `acme-roofing.com`) says the vendor changed banks. The agent pays the vendor's *current* account at execution time. Every step was valid, the ledger balances, and \$40,000 went to an attacker.

We kept asking what a controller would need to see before letting an AI run accounts payable. Our answer: every action checked before money moves, and checks that improve because someone keeps attacking them. So we built both sides: one that attacks and one that defends.

### What it does

Vandal has three parts:

| | **The Operator** | **Vandal Guard** | **Vandal Strike** |
|---|---|---|---|
| Role | The AI finance agent doing the work | The security checkpoint in front of the money | The ethical hacker |
| Does | Reads messy invoices (email bodies, OCR'd scans, forwarded threads), codes the GL, gets approvals, runs payments, reconciles, recovers misdirected money | Checks every tool call (pay, change vendor bank details, refund, post an entry) against independent records, then **allows, holds, or escalates**, with an audit trail and cited explanations | Clones the company into a deterministic *financial twin*, searches for attack sequences, diagnoses the root cause, synthesizes a control, and proves it |
| When | Always | Online, on every action | Offline, before deployment and after every change |

Guard doesn't trust what the Operator says. It walks the **authorization chain**:

$$
\text{obligation} \rightarrow \text{approval} \rightarrow \text{execution} \rightarrow \text{settlement} \rightarrow \text{books}
$$

At each link it asks whether this action matches what was actually approved, which accounts are verified, and what the bank feed says. The Operator can't approve its own work, the synthesizer can't approve its own patch, and pushback never clears a hold.

**The self-healing loop:** *Operate → Attack → Diagnose → Fix → Prove → Approve → Enforce.*

1. Strike clones the live company and attacks the clone.
2. Search finds a sequence Guard's current controls let through, even though every step is individually valid and the ledger balances.
3. Strike computes the root cause, the broken link in the chain.
4. A synthesizer proposes controls from a fixed template library. Search attacks each candidate, and any candidate that lets an attack through *or* blocks a legitimate payment is refuted.
5. A human controller approves the surviving control in the inbox.
6. Guard enforces it, and Strike replays the original attack: **HELD, \$0.**

Fixes go into Guard's controls, never into the model: no retraining and no prompt edits. The protection works no matter which agent sits in the Operator's seat, because any agent can plug in through the `FinanceOperator` interface.

**From an actual run** (v0 against `v1-synth`, the policy CEGIS synthesized live: approval binding plus verified account changes):

| | v0 | v1-synth |
|---|---|---|
| Violations found by search | 12 | 0 |
| Attack success (40 held-out variants) | 100% | 0% |
| Exposure | \$300,787 | \$0 |
| Legitimate payments blocked | 0 | 0 |
| Intake field accuracy (120 fields, 24 messy documents) | 100% | 100% |

### How we built it

**The twin is a pure function.** Every run is a fold over a seed and an event log:

$$
S_n = \operatorname{fold}(\delta,\ S_0(\text{seed}),\ [e_1, \dots, e_n]), \qquad \operatorname{hash}(S_n) \text{ is reproducible}
$$

Money is integer cents, time is a simulated clock, and nothing reads the wall clock. The same seed and events always give the same state hash. That determinism is what makes replay, minimization, and proof possible.

**Strike's search** is a bounded breadth-first search over an alphabet $\Sigma$ of attacker and fault moves (bank-detail changes, lookalike emails, forged callbacks, dropped bank acks, late feeds), with state-hash deduplication and partial-order reduction. A sequence is a violation when it breaks one of eleven invariants, checked against hidden oracle labels that no agent can read. Delta debugging shrinks a violation down to a minimal counterexample. For Scenario A that's **one move**.

**Exposure** is the money that reached an account the oracle labels as attacker-controlled:

$$
\text{Exposure}(S) = \sum_{p \,\in\, \text{payments}(S)} \text{amount}(p)\cdot \mathbf{1}\left[\text{payee}(p) \in A_{\text{attacker}}\right]
$$

**Synthesis is CEGIS** (counterexample-guided inductive synthesis) over six control templates, T1–T6: verified account change, approval binding, idempotent execution, and others. A candidate policy $\pi$ survives only if

$$
\forall\, \sigma \in \Sigma^{\le k}:\ \neg\,\text{violates}(\pi, \sigma) \quad\wedge\quad \text{blocks}(\pi, \text{legit}) = \varnothing
$$

Every counterexample that beats a candidate goes back into the next proposal. Lints reject overfit candidates, spoofable ones (a callback that accepts a video call), and candidates that block where a hold would work.

**Verification** runs six checks: replay, re-search at the same depth, 40 held-out variants the synthesizer never saw, a 25-case regression suite, legitimate operations, and the invariants. For `v1-synth` at depth 3 that meant 34,676 sequences re-searched, no violation, and all 80 seeded invoices paid. Our claims are bounded: no violating sequence of length $\le k$ within the modeled moves. We don't claim more than that.

**Claude proposes, and deterministic code decides:**
- **Claude Sonnet** is the Operator's intake. It reads the messy invoices and writes Guard's cited explanations.
- **Claude Opus** proposes controls inside the CEGIS loop and turns a judge's plain-language threat ("a vendor emails new bank details, then calls to confirm") into moves Strike can run.
- Every call goes through one wrapper with structured output and a content-keyed cache. `DEMO_PLAYBACK` replays the whole demo offline with zero cache misses.
- Search and verification always run the deterministic reference Operator, so money outcomes never depend on a model's sampling.

**The stack:**
- **Backend:** Python 3.12, FastAPI, Pydantic, and SQLAlchemy (SQLite or Postgres for persistence), managed with uv and tested with pytest and ruff.
- **War room:** Next.js, React, TypeScript, Tailwind, and zustand, with live updates over server-sent events. Strike's search sits on one side, Guard's verdict feed and approvals inbox on the other, and the twin's authorization chains in the middle.
- **Tooling:** an in-browser mock API recorded from the real backend, a smoke script that drives the entire loop over HTTP, and GitHub Actions CI on every PR.

### Challenges we ran into

- **Structured output can't fill an open dictionary.** Strike's threat reader and the CEGIS proposer asked Claude for a free-form `params` dict. The schema only admitted an empty object, so every move came back with `params: {}`. That failure was silent: every Claude-planned attack was "outside the attacker's capabilities," and every proposed control used default parameters. We found it while recording the cache. We moved the parameters into lists of `{key, value}` pairs and fold them into the dict in code.
- **Cache keys that couldn't be recomputed.** A server-side model fallback stored the *answering* model in the request, so the content key no longer matched its own file. Entries now store the requested model plus `served_by`, and a test recomputes every key and greps the cache for secrets.
- **State explosion.** A naive search over even a small alphabet blows up fast. State-hash deduplication and partial-order reduction (independent moves commute) kept a depth-3 re-search to about 35k sequences.
- **Overfitting in synthesis.** The first controls CEGIS found beat the one counterexample they had seen and nothing else. Held-out variants, the spoofability lint, and the "don't block legitimate payments" constraint are what make a synthesized control trustworthy.
- **Demo-killers found by clicking through it.** The "Try your own scenario" form posted to the live run while its button named the replay's policy, so a held attack looked like it got through. Separately, running the loop a second time in one server crashed Verify. Both were fixed by driving the real war room end to end.
- **What's still open:** Scenario F (a refund after two deposits) can't auto-repair at depth 3, only at depth 2. The template library either needs a parameter it lacks, or the invariant counts a refund of the attacker's own cleared money as a loss. We left the bound visible rather than hiding it.

### What we learned

- **A balanced ledger proves nothing about where the money went.** Double-entry bookkeeping catches arithmetic, not authorization. The useful question is whether each payment matches what was approved, and that needs the whole chain.
- **Check against records, not words.** An agent can be persuaded, and so can a check that reads prompts. Guard only trusts independent records: the approved instruction, verified accounts, the bank feed, the ledger. That's why talking to it doesn't move a hold.
- **LLMs are great proposers and poor deciders.** Claude was excellent at reading ugly invoices, writing explanations with citations, and suggesting controls. It was never the thing that decided whether money moved. Putting a verifier behind every proposal made the system both creative and trustworthy.
- **Determinism is a feature you design in on day one.** Integer cents, a sim clock, and `fold(seed, events)` made everything else possible: replay, minimization, regression, and a demo that runs offline.
- **State bounded claims honestly.** "No violation of length $\le 3$ within these moves" is something a controller can sign off on. "Secure" isn't.

### What's next

- **Sources that disagree:** invoices above the contracted rate, and bank feed lines that come in net of wire fees.
- **Scenario D:** split and duplicate invoices (templates T4 and T5).
- **Re-validating a held invoice** when its receipt arrives later.
- **A customer's own agent:** plugging a company's own finance agent into the `FinanceOperator` seat, so Strike attacks *their* agent and Guard protects *their* payments.

---

## Built with

_(22 of 25 tags.)_

`python` · `fastapi` · `pydantic` · `sqlalchemy` · `sqlite` · `postgresql` · `uvicorn` · `uv` · `pytest` · `ruff` · `anthropic` · `claude` · `claude-opus` · `claude-sonnet` · `next.js` · `react` · `typescript` · `tailwindcss` · `zustand` · `server-sent-events` · `node.js` · `github-actions`

## Try it out

- GitHub repo: https://github.com/angadsingharora/vandal (make it public or add the judges first)
- Run it: `python scripts/demo.py --playback`, then open http://localhost:3000. No API key or network is needed.

---

## Additional info (for judges and organizers, not public)

**Sponsor / special prizes** (suggested; check every one you're eligible for):
- [Hyphenate] The Hyphenated Enterprise: Autonomous Systems for Finance (primary track)
- [Armadin] Best Security Hack
- [Atlassian] Best Agent / Best Security Solution for Agents
- Cal Hacks Most Technically Complex Hack

**Emails used to apply to Cal Hacks 13.0:** _(not kept in the repo, which will be public; paste them from the team's notes)_

**Universities or schools:**
- University of California, Berkeley
- University of Washington, Seattle

**GoDaddy Registry domains:** none

**Which AI tools did you use this weekend?** Anthropic

**Did you implement a generative AI model or API in your hack? How and why?**

> Yes, the Anthropic Claude API, in four places, all through one wrapper (`backend/vandal/llm.py`) with structured output and a content-keyed cache:
> 1. **The Operator's intake (Claude Sonnet)** reads messy vendor documents (email bodies, OCR'd scans, forwarded threads) into structured invoices and GL codes: 120/120 fields and 24/24 GL codes on our test set.
> 2. **Strike's threat reader (Claude Opus)** turns a plain-language threat into attack moves the search engine can run, and writes the attacker's content (lookalike emails, pressure messages).
> 3. **The CEGIS proposer (Claude Opus)** suggests candidate controls. Every candidate is attacked by deterministic search, and refuted ones feed back into the next proposal.
> 4. **Guard's explanations (Claude Sonnet)** answer "why was this payment held?" with every claim citing a record id. Pushback never changes the verdict.
>
> Why: Claude handles the unstructured, open-ended parts (messy documents, new threats, creative fixes), and deterministic code decides whether money moves. That way the system can take on new attacks without ever letting a model's output move money unchecked. The cache also lets the full demo replay offline.

**Feedback on technology used:**

> **Anthropic Claude API:** Structured output with Pydantic schemas made it easy to treat Claude as a typed function, and Opus's control proposals got noticeably better when we fed back the counterexample that beat the last candidate. One sharp edge: a schema with a free-form `dict` silently comes back empty, so the model put the values in its notes instead. A validation warning there would have saved us hours. Server-side fallback was useful for reliability, but the response's `model` differing from the request is worth calling out in the docs for anyone caching by request content.
>
> **Next.js + server-sent events:** SSE was the simplest way to stream search progress and CEGIS iterations into the war room. No websocket server was needed.
>
> **uv:** It made the Python setup reproducible across macOS and Windows teammates. `uv run` from a clean checkout just worked.

---

## Appendix: for the video and the judges

These aren't Devpost fields. They're here for recording the video and answering judges' questions.

### Video script (3:00)

| t | Action | What's on screen |
|---|---|---|
| 0:00 | — | "Your books can balance while the money goes to the wrong person." |
| 0:10 | **Run operations** | The Operator processes 80 invoices, gets the controller's approval for the $40k contractor invoice, pays, posts, reconciles. Every tool call shows Guard's verdict. Everything green. |
| 0:35 | **Release Vandal Strike** | The live sequence counter; 12 violating traces; the minimal counterexample is **one move**: a lookalike-domain email changing the vendor's bank details after approval, before the batch. Every step valid, ledger balanced. Exposure: **$40,000**. |
| 1:00 | **Replay on twin → Diagnose** | The Attack tab: the payment, the attacker's account (Judge view reveals the answer key). The authorization chain with the execution link broken: *"executed payee ≠ approved payee; nothing binds execution to the approval."* |
| 1:20 | **Synthesize a control** | CEGIS live, with Claude proposing: T2 approval binding → search beats it with a change *before* approval → T2 + T1 verified account change survives; a T1 that accepts video calls is refuted by the spoofable lint. Scores on screen. |
| 2:00 | **Verify → Submit → Approve as Controller → Apply** | Six checks pass; the evidence pack and policy diff go to the inbox; a human signs off. The Operator can't. |
| 2:10 | **Replay under v1-synth** | Same counterexample: **HELD, $0**, every invariant holds. Then "a vendor emails new bank details after approval, then calls to confirm" from the inject form: the deepfake confirmation is held too. |
| 2:35 | **Scenario B** | `drop_ack → retry → double payment`; the synthesized T3 makes execution idempotent. "Jepsen for financial agents." |
| 2:55 | — | "Every gap Strike finds becomes a control Guard enforces." |
| after | **Try your own scenario** / **why?** | A judge describes a threat in plain language; Claude maps it onto moves, it runs through the same loop live. Ask Guard why a payment was held and push back: every claim cites an id, and the hold stands. |

### What's real, what's simulated, and how we know

| Real | Simulated | How we know it works |
|---|---|---|
| Double-entry ledger, invariants, policy gate, bounded search, CEGIS verification (deterministic code with tests) | The company, vendors, bank accounts, and money | Hidden oracle labels act as an answer key no agent can read |
| Claude reading every document, proposing controls, and explaining with citations | Callbacks, deepfakes, and counterparty agents, modeled as channel events with forgeable attributes; no synthetic media | Held-out variants the synthesizer never saw, plus a re-search under the new policy |
| The synthesizer proposing controls, and search refuting or accepting them | Bank behavior and faults (timeouts, dropped acks, late feeds) | The scorecard: before-and-after rates from actual runs |
| Replay of any recorded trace | Approvers, when no human is present | Replay-determinism tests |

Models propose; code decides. Search and verification always run the deterministic reference Operator, so money outcomes never depend on a model's mood.
