# Vandal

**Break it. Fix it. Prove it.**

Vandal is a red team and a blue team for AI that runs a company's money. It was built for Cal Hacks 13.0 (Hyphenate track: *The Hyphenated Enterprise: Autonomous Systems for Finance*).

- **Red (Vandal Sandbox)** clones the company's financial system into a deterministic *financial twin*. It then searches for sequences of events that break financial invariants, finds the root cause, and synthesizes a control that closes the gap. Before anyone sees that control, Red has already verified it.
- **Blue (Vandal Guard)** sits in the live path. Before any money moves, it checks each action the finance agent takes (pay, change vendor bank details, refund, post an entry) against an independent source of truth. It allows, holds, or escalates the action and records the evidence.
- **The Operator** is the finance agent that Blue protects and Red tests. It plugs in through the `FinanceOperator` interface, so any agent can take its place.

Every gap Red finds becomes a control that Blue enforces. Fixes go into Blue's controls. The agent itself is never retrained, and its prompts are never edited.

> Your books can balance perfectly while the money goes to the wrong person.

## How the loop works

1. **Operate.** The Operator does a 12-property real-estate manager's AP work (intake, approvals, payment runs, ledger, reconciliation), and Blue gates every tool call.
2. **Search.** Bounded search over the attacker and fault alphabet finds a minimal counterexample. In it, every step looks valid and the ledger balances, but $40,000 goes to an attacker's account.
3. **Diagnose.** Authorization-coverage analysis walks the chain (obligation → approval → execution → settlement → books) and names the broken link, e.g. *"executed payee ≠ approved payee; nothing binds execution to the approval."*
4. **Synthesize.** A CEGIS loop proposes controls from a fixed set of templates (T1–T6). Search attacks each candidate. A candidate fails if the attack gets through or if it blocks legitimate payments.
5. **Verify.** The surviving control has to pass replay, re-search, held-out variants, regression, legitimate-ops impact, and invariant checks. The results go into an evidence pack for a human to approve.

## Run the whole demo with one command

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/) (`python -m uv` works when `uv` isn't on PATH) and Node 20+.

```bash
python scripts/demo.py --playback
```

That starts the API on `:8000` and the war room on `:3000` (running `npm install` the first time), with **playback** on: every Claude call is served from the recordings in `backend/llm_cache/`, so the demo needs no network and no API key. Drop `--playback` to call Claude live (put `ANTHROPIC_API_KEY` in `backend/.env`), or use `--mock` for the war room alone, replaying fixtures recorded from the backend. The Playback switch in the top bar flips the same flag on a running server.

The loop a judge sees, in order: **Reset demo → Run operations → Unleash Vandal → Replay on twin → Diagnose → Synthesize a control → Verify → Submit for approval → Approve as Controller → Apply → Replay under the new policy**, then **Try your own scenario**, **why?** on any payment, and the **Scorecard**. `backend/scripts/demo_smoke.py` drives the same loop over the API and asserts the numbers below; `uv run pytest --slow` runs it.

## Quickstart (CLI)

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync
cp .env.example .env   # optional: database URL, API key, search depth
```

Try the core scenario (Scenario A, the approval/execution gap):

```bash
uv run vandal seed                                            # the seeded company
uv run vandal run --days 5                                    # legitimate operations, all green
uv run vandal attack --trace scenarios/a_manual.json          # v0 controls: $40k misdirected
uv run vandal attack --trace scenarios/a_manual.json --policy v1   # v1 controls: held
uv run vandal search --scenario a                             # find the counterexample by itself
uv run vandal synth --no-llm --scenario a                     # diagnose + CEGIS + verify (~2 min)
```

`synth` writes an evidence pack to `backend/evidence/`.

The Operator's intake (O1) reads messy documents: invoices as email bodies, OCR'd scans with typos, forwarded threads, and line-item tables, each with a hidden answer key. `uv run vandal intake` scores it (the scorecard reports the same numbers), and `uv run vandal run --operator llm` runs the company with the LLM Operator; without a model configured, its deterministic reader does the reading.

## CLI

| Command | What it does |
|---|---|
| `vandal seed` | Print the seeded company summary |
| `vandal run` | Run legitimate operations for N business days (`--days`, `--persist`, `--operator reference\|llm`) |
| `vandal attack` | Replay a hand-written adversary trace (`--trace`) |
| `vandal search` | Bounded adversarial search (`--scenario a\|b\|f`, `--depth`, `--workers`, `--exhaustive`) |
| `vandal synth` | Diagnose and synthesize a control with CEGIS (`--scenario`, `--no-llm`) |
| `vandal verify` | Run the verification suite against a policy (`--policy`, `--parent`) |
| `vandal inject` | Run a threat described in plain language, or a composed trace (`--trace`, `--dry-run`) |
| `vandal rebuild` | Rebuild a persisted run from its events and check its state hash |
| `vandal intake` | Score the LLM Operator's intake on the messy-document items: field and GL-coding accuracy (`--no-llm`, `--show MSY-003`) |

Most commands take `--profile` (default `bayline`), `--seed`, and `--policy` (`v0`, a name under `backend/policies/`, or a JSON path). Run `uv run vandal <command> --help` for the rest.

### Scenarios

| | Threat | Gap | Control |
|---|---|---|---|
| **a** | Vendor bank details change after approval, before the payment run | Approval binding, verification channel | T1 `VerifiedAccountChange` + T2 `ApprovalBinding` |
| **b** | Bank drops an ack, the Operator retries, the vendor is paid twice | Execution idempotency | T3 `IdempotentExecution` |
| **c** | Scenario A plus a cloned-voice inbound "confirmation" of the bank change (`scenarios/c_deepfake.json`) | Spoofable verification channel | T1 with `accepted_channels` excluding inbound calls; a T1 that accepts them is beaten, and the spoofable lint rejects it |
| **f** | Overpayment, then a refund request to a different account | Refund redirection | T6 `RefundToSource` |

Policies `v1` → `v2` → `v3` in `backend/policies/` add these controls in turn on top of the `v0` baseline.

## API

```bash
cd backend
uv run uvicorn vandal.api.main:app --reload
```

FastAPI app with SSE for live updates. It covers runs (`/demo/reset`, `/runs`, `/runs/{id}/operate`, `/state`, `/entities`, `/ledger`, `/chain/{payment}`, `/events`, `/inject`), jobs (`/search`, `/diagnose`, `/synthesize`, `/verify`, `/jobs/{id}/events`), Blue (`/runs/{id}/verdicts`, `/approvals`, `/policies/{version}/apply`, `/explain/{type}/{id}`), `/replay`, `/metrics`, `/policies`, and `/settings`. Runs live in memory. When `DATABASE_URL` is set (SQLite, or Postgres/Supabase through the `postgres` extra), runs, events, searches, syntheses, and evidence packs are also persisted. CORS origins come from `VANDAL_CORS_ORIGINS`, which defaults to `http://localhost:3000`.

## War room

```bash
cd frontend
npm install
npm run dev        # against the API on :8000
npm run dev:mock   # no backend: a mock API recorded from the real one
```

See [frontend/README.md](frontend/README.md) for the demo loop.

## Tests

```bash
cd backend
uv run pytest          # fast suite, ~10 s
uv run pytest --slow   # adds full searches, CEGIS, and verification packs; run before a PR
uv run ruff check .
```

## Scorecard, from an actual run

`GET /metrics` (the war room's Scorecard dialog) at search depth 1, v0 against the policy CEGIS synthesized in the demo (`v1-synth` = T2 `ApprovalBinding` + T1 `VerifiedAccountChange`). Verification of `v1-synth` at depth 3: 34,676 sequences re-searched with no violation, 0 of 40 held-out variants succeeded, 25 of 25 regression cases passed, all 80 seeded invoices paid with 0 holds and 0 blocks.

| | v0 | v1-synth |
|---|---|---|
| Sequences explored (depth 1) | 65 | 65 |
| Violations found | 12 | 0 |
| Attack success rate (held-out variants) | 100% | 0% |
| Exposure | $300,787 | $0 |
| Legitimate operations run / failed / blocked | 105 / 7 / 0 | 105 / 0 / 0 |
| Holds on legitimate operations (friction) | 0 | 9 |
| False-positive rate | 6.7% | 0.0% |
| Broken invariants in legitimate runs | INV-2, INV-5 | none |
| Intake: field accuracy (120 fields, 24 messy documents) | 100% | 100% |
| Intake: GL-coding accuracy (24 documents) | 100% | 100% |

Every number comes from `backend/vandal/verify/` running on fresh clones against the hidden oracle labels; none is typed in. The 7 legitimate failures under v0 are the regression suite's real bank changes, which v0 has no way to verify.

## What's real, what's simulated, and how we know

| Real | Simulated | How we know it works |
|---|---|---|
| Double-entry ledger, invariants, policy gate, bounded search, CEGIS verification (deterministic code with tests) | The company, vendors, bank accounts, and money | Hidden oracle labels act as an answer key no agent can read |
| Claude reading every document, proposing controls, and explaining with citations | Callbacks, deepfakes, and counterparty agents, modeled as channel events with forgeable attributes; no synthetic media | Held-out variants the synthesizer never saw, plus a re-search under the new policy |
| The synthesizer proposing controls, and search refuting or accepting them | Bank behavior and faults (timeouts, dropped acks, late feeds) | The scorecard: before-and-after rates from actual runs |
| Replay of any recorded trace | Approvers, when no human is present | Replay-determinism tests in `backend/tests/` |

## What we can and can't claim

| Can claim | Can't claim |
|---|---|
| "No violating sequence of length ≤ k within the modeled actions and capabilities" | "Mathematically proven safe" |
| "The root cause is computed from the authorization chain" | "Finds every possible failure" |
| "The control was verified by replay, re-search, held-out variants, and regression" | "Works on your real systems today" |
| "Exposure" | "Losses prevented" |
| "Synthesizes controls from a bounded template library" | "Rewrites arbitrary financial software" |

## Design principles

- **Deterministic.** Every run is `fold(seed, events)`, so the same seed and the same events give the same `state_hash`. Time comes only from the sim clock, and money is always integer cents.
- **Models never change state.** Money math, gating, search, and verification are deterministic code. The AI proposes. Search and verification decide.
- **Every state change passes Blue's gate**, in search, in verification, and in the live demo.
- **Bounded claims.** "No violation" means none within the searched depth and alphabet, verified by replay and re-search. It is not a proof beyond that.

## Repo layout

```
backend/
  vandal/
    contracts/   shared entities, events, moves, controls, verdicts, interfaces
    twin/        financial twin: state, reducer, seed, bank simulator, ledger, flows
    search/      action alphabet, BFS, partial-order reduction, minimization, Red content
    synth/       root cause (coverage), control templates, lints, CEGIS
    verify/      invariants, oracle, replay, regression, variants, evidence pack
    guard/       Blue: gate, checks, authorization chain, SoD, approvals, explanations
    operator/    the reference Operator (and the LLM Operator)
    api/         FastAPI, SSE, persistence
    cli.py
  profiles/      company profiles (bayline.yaml)
  policies/      control policies v1–v3
  scenarios/     hand-written adversary traces
  tests/
frontend/        war-room UI (Next.js): search, twin, chains, verdicts, inbox, CEGIS, inject
docs/            spec, design, implementation plan, reviews
```

## Status

The Sandbox (twin, search, root cause, CEGIS, verification), fault injection, money in, persistence, the API skeleton, the Operator (reference and LLM intake, recovery, approvers), and the war-room frontend (F0–F6) are in. The LLM layer (L0, `vandal/llm.py`) is in: Claude through one wrapper with structured output and a content-keyed cache under `backend/llm_cache/`. `DEMO_PLAYBACK=true` serves every call from that cache with no API key, and any miss, timeout, or missing key makes the caller take its deterministic path (`--no-llm` forces it). See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for the slice plan.

## Docs

- [SPEC.md](docs/SPEC.md): the original product brief
- [DESIGN.md](docs/DESIGN.md): the design (architecture, twin, invariants, search, synthesis, verification, demo)
- [IMPLEMENTATION.md](docs/IMPLEMENTATION.md): build order and conventions
- [PLAN_REVIEW.md](docs/PLAN_REVIEW.md), [DESIGN_CRITIQUE.md](docs/DESIGN_CRITIQUE.md): reviews

## Authors

Angad Arora, Dhruv Kasarabada, and team.
