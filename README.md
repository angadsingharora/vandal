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

## Quickstart

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

## CLI

| Command | What it does |
|---|---|
| `vandal seed` | Print the seeded company summary |
| `vandal run` | Run legitimate operations for N business days (`--days`, `--persist`) |
| `vandal attack` | Replay a hand-written adversary trace (`--trace`) |
| `vandal search` | Bounded adversarial search (`--scenario a\|b\|f`, `--depth`, `--workers`, `--exhaustive`) |
| `vandal synth` | Diagnose and synthesize a control with CEGIS (`--scenario`, `--no-llm`) |
| `vandal verify` | Run the verification suite against a policy (`--policy`, `--parent`) |
| `vandal inject` | Run a threat described in plain language, or a composed trace (`--trace`, `--dry-run`) |
| `vandal rebuild` | Rebuild a persisted run from its events and check its state hash |

Most commands take `--profile` (default `bayline`), `--seed`, and `--policy` (`v0`, a name under `backend/policies/`, or a JSON path). Run `uv run vandal <command> --help` for the rest.

### Scenarios

| | Threat | Gap | Control |
|---|---|---|---|
| **a** | Vendor bank details change after approval, before the payment run | Approval binding, verification channel | T1 `VerifiedAccountChange` + T2 `ApprovalBinding` |
| **b** | Bank drops an ack, the Operator retries, the vendor is paid twice | Execution idempotency | T3 `IdempotentExecution` |
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

## Design principles

- **Deterministic.** Every run is `fold(seed, events)`, so the same seed and the same events give the same `state_hash`. Time comes only from the sim clock, and money is always integer cents.
- **Models never change state.** Money math, gating, search, and verification are deterministic code. The AI proposes. Search and verification decide.
- **Every state change passes Blue's gate**, in search, in verification, and in the live demo.
- **Bounded claims.** "No violation" means none within the searched depth and alphabet. It is not a proof beyond that.

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

The Sandbox (twin, search, root cause, CEGIS, verification), fault injection, money in, persistence, and the API skeleton are in. The war-room frontend (F0–F6) is in. Still in progress: the LLM layer (`vandal/llm.py`; until it lands, callers fall back to deterministic paths such as `--no-llm`). See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for the slice plan.

## Docs

- [SPEC.md](docs/SPEC.md): the original product brief
- [DESIGN.md](docs/DESIGN.md): the design (architecture, twin, invariants, search, synthesis, verification, demo)
- [IMPLEMENTATION.md](docs/IMPLEMENTATION.md): build order and conventions
- [PLAN_REVIEW.md](docs/PLAN_REVIEW.md), [DESIGN_CRITIQUE.md](docs/DESIGN_CRITIQUE.md): reviews

## Authors

Angad Arora, Dhruv Kasarabada, and team.
