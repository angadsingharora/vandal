# Vandal — Implementation Plan

This is the build order for [DESIGN.md](DESIGN.md) v0.6. **Red (the Sandbox) comes first**, split into vertical slices. Each slice is runnable, tested, and demoable before the next one starts. Blue, the Operator, the LLM layer, the API, and the frontend follow in the same style.

**Rules for every slice:**
- It isn't done until its "Done when" test passes (`uv run pytest`) and its CLI or API command works.
- Build the thinnest end-to-end version first, then widen it. For example, get one invoice through end to end before handling all 80.

---

## 0. Conventions (everyone)

| Topic | Decision |
|---|---|
| Language and tools | Python 3.12, `uv`, Pydantic v2, FastAPI, pytest, ruff |
| Money | Integer cents everywhere (`Cents = int`). No floats |
| Time | Sim clock only. `datetime.now()` is banned outside `api/` (enforced by a lint test) |
| Determinism | Every run is `fold(seed, events)`. Same seed + same events = same `state_hash` |
| IDs | Stable business keys (`V-007`, `INV-1042`, `PAY-0001`), the same across clones |
| State changes | Only through `Tools.call`, and **every call passes Blue's gate**, from the very first slice. There's no "stub mode" to remove later |
| Operator in search | Search and verification always use the **deterministic reference Operator**. The LLM Operator runs in the live demo. Blue enforces the same controls on both, so money outcomes don't depend on which one runs |
| LLM | Only through `vandal/llm.py` (slice L0). It's called from `operator/llm_operator.py`, `search/red.py`, `synth/propose.py`, and `guard/explain.py`. Every call is cached by `(prompt_version, agent, step, sha256(input))` |
| Import boundaries | `twin/ search/ synth/ verify/ guard/` never import from `operator/` implementations (enforced by a test) |
| Branches | One branch per slice, named `slice/R3-first-violation`. PR into `main` once its test is green |
| Canonical layout | §1 below. DESIGN §16 points here |

## 1. Repo skeleton

```
vandal/
  backend/
    pyproject.toml
    vandal/
      cli.py                      # vandal seed | run | attack | search | synth | verify | inject
      llm.py                      # L0: Claude wrapper, structured output, cache, playback
      contracts/                  # frozen at the end of R0, shared by every part
        entities.py  events.py  moves.py  controls.py  verdicts.py  interfaces.py
      twin/                       # RED: financial twin
        clock.py  state.py  reducer.py  seed.py  profile.py  world.py
        bank.py  ledger.py  flows.py  evidence.py  money_in.py
      search/                     # RED: adversarial search
        alphabet.py  bfs.py  minimize.py  por.py  workers.py  red.py
      synth/                      # RED: root cause + synthesis
        coverage.py  templates.py  lint.py  propose.py  cegis.py  objective.py
      verify/                     # RED: verification
        invariants.py  oracle.py  replay.py  regression.py  variants.py  evidence_pack.py
      guard/                      # BLUE: runtime verification layer
        gate.py  checks.py  chain.py  sod.py  approvals.py  explain.py
      operator/                   # OPERATOR: the agent being protected
        reference.py  llm_operator.py
      api/                        # FastAPI, SSE, persistence
        main.py  registry.py  sse.py  routes_*.py  db.py
    profiles/bayline.yaml
    scenarios/                    # hand-written traces (a_manual.json, ...)
    tests/
  frontend/                       # Next.js war room
  docs/
```

## 2. Shared contracts (frozen at the end of R0)

Everyone codes against these. Any change after the freeze needs agreement from the whole team.

```python
# contracts/interfaces.py
class Tools(Protocol):            # the only way to change state; always runs Blue's gate
    def call(self, actor: Actor, name: str, args: BaseModel) -> ToolResult: ...

class Guard(Protocol):            # Blue
    def check(self, state: State, action: Action, stage: Stage) -> Verdict: ...

class FinanceOperator(Protocol):  # the Operator
    def on_event(self, ev: ChannelEvent, tools: Tools) -> None: ...
    def on_case(self, case: Case, tools: Tools) -> None: ...

# contracts/moves.py: one adversary or environment step, discretized so search can enumerate it
class Move(BaseModel):
    kind: Literal["change_request", "inbound_confirmation", "submit_invoice", "fault",
                  "trigger_batch", "retry", "deposit", "refund_request", "tick"]
    params: dict[str, str | int]
    at: int                       # insertion point in the World schedule (timing)

# contracts/controls.py
class Check(BaseModel):           # what the gate actually runs
    stage: Stage
    when: Predicate               # over deterministic facts
    action: Literal["allow", "hold", "escalate", "block"]
    require: Requirement | None   # evidence that clears a hold

class Control(BaseModel):         # what synthesis produces; compiles to Checks
    template: Literal["T1", "T2", "T3", "T4", "T5", "T6"]
    params: dict[str, str | int | list[str]]
    def compile(self) -> list[Check]: ...

# contracts/verdicts.py
class Verdict(BaseModel):
    decision: Literal["allow", "hold", "escalate", "block"]
    fired: list[str]              # check ids
    facts: dict[str, Any]         # the facts evaluated (the evidence)
    cites: list[str]              # event, approval, and evidence ids
```

## 3. Owners (team of 4)

| Owner | Area | Slices |
|---|---|---|
| **P1: Twin + gate** | the twin, flows, ledger, Blue's gate core, money in | R0, R1, R2, R3, R6 (checks + evidence), B2, R11 |
| **P2: Search + synthesis** | search, root cause, templates, CEGIS, faults | R0, R4, R5, R6 (templates + lints), R8, R10 |
| **P3: LLM + Operator + Blue's human side** | LLM wrapper, LLM Operator, Red content, SoD and approvals, explanations | L0, O1, O2, R9, B3, B5, O3 |
| **P4: Product surface** | API, verification suite and scorecard, persistence, frontend | A0, R7, B4, R12, F0–F6 |

---

## 4. RED — Vandal Sandbox (build first)

**Critical path:** R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8 (milestones M1–M3). Everything after that is M4–M5.

**Parallel work:**
- P2 starts R4's alphabet and BFS against `twin/state.py` as soon as R1 lands.
- P4 starts R7's regression fixtures and A0 right after R0.
- P3 starts L0 right after R0.

---

### R0 — Skeleton and contracts · ~1.5h · P1+P2
**Build:**
- `pyproject.toml`, the layout from §1, and ruff/pytest config.
- All `contracts/` models from §2.
- `cli.py` with stub commands.
- Lint tests for the import boundaries and the `datetime.now` ban.

**Done when:** `uv run pytest` passes, `uv run vandal --help` lists the commands, and **the team agrees the contracts are frozen.**

---

### R1 — Deterministic twin and seed · ~2.5h · P1
**Build:**
- **`profiles/bayline.yaml`:**
  - 25 vendors, with contacts, contact history, and verified accounts;
  - about 60 POs and receipts, and about 80 invoices, including one $40k contractor invoice for Scenario A;
  - bank accounts of $1.8M and $200k;
  - the chart of accounts and approval matrix;
  - attacker capabilities and risk appetite (λ, μ).
- **`seed.py`:** a fixed RNG produces the seed state.
- **`state.py`:** `State`, `clone()`, `state_hash()`.
- **`clock.py`:** a business-day clock.
- **`reducer.py`:** `apply(state, event) -> state`, a pure function.

**Done when:**
- Five seeds in a row give the same `state_hash`.
- `clone()` is independent: changing the clone doesn't touch the original.
- `vandal seed` prints the company summary.

---

### R2 — Money-out happy path, gate core, ledger · ~4h · P1
**Build, thin path first:**
1. **One invoice end to end.**
   - **Flows:** `received → validated (3-way match) → approved → scheduled → instruction built → submitted → acknowledged → settled → posted → reconciled`.
   - **v0 realism:** the instruction reads the vendor's **current** bank account at execution time.
2. **`guard/gate.py` + `guard/checks.py` (Blue core).** Every `Tools.call` goes through the gate at its stage and returns a `Verdict`. The gate runs the **v0 controls**, written as `Check`s: 3-way match, the $25k approval threshold, exact duplicate number, active vendor. The most restrictive matching check wins.
3. **`bank.py`:** submit → ack; settlement at T+1 as a `BankTransaction`. No faults yet.
4. **`ledger.py`:** append-only journal entries (DESIGN §12) and reversal entries.
5. **`twin/world.py`:** a deterministic World schedule of legitimate events over N business days.
6. **`operator/reference.py`:** a deterministic, no-LLM Operator, plus the simulated approver (approves when the PO matches and the vendor has 3+ prior payments).
7. **Widen** to all pending invoices.

**Done when:**
- `vandal run --days 5` pays every legitimate invoice.
- Every tool call has a recorded `Verdict`.
- INV-1 holds (entries balance), and INV-7 holds (GL cash = bank − in-flight, AP subledger = control account).

---

### R3 — Invariants, oracle, and the first violation (Scenario A by hand) · ~2.5h · P1
**Build:**
- **`verify/invariants.py`:** INV-1 through INV-7 and INV-9 as pure functions `check(state) -> list[Violation]`.
  - INV-8 (append-only) is a structural test here.
  - INV-10 comes in B3, and INV-11 in R11.
- **`verify/oracle.py`:** harness-only labels such as `attacker_controlled`. A test asserts that `Tools` can never read them.
- **First adversary move:** `change_request(vendor, fields=bank, channel=email, sender=lookalike)`.
- **`verify/replay.py`:** `replay(seed, moves) -> RunResult`, returning violations, exposure, and the final hash.
- **`scenarios/a_manual.json`:** approve the $40k invoice → `change_request` → `trigger_batch`.

**Done when:**
- Replaying the trace gives INV-2 and INV-4 violations with **exposure = 4,000,000 cents**, and INV-1 still holds (the books balance).
- Same trace, same hash.
- `vandal attack --trace scenarios/a_manual.json` prints the violation.

---

### R4 — Bounded search · ~4h · P2
**Build, in this order:**
1. **`search/alphabet.py`:** the moves from DESIGN §8.1, with discretized parameters, filtered by attacker capabilities. A move's `at` field is an insertion point between consecutive World events in the scenario window, which is how timing gets represented.
2. **`search/bfs.py`:** breadth-first search up to `SEARCH_DEPTH`, with **state-hash deduplication**.
3. **`search/minimize.py`:** delta debugging down to the shortest violating trace.
4. **Benchmark:** report runs per second and ms per run.
5. **Only if depth 4 takes more than 60 seconds:** `search/por.py` (moves that touch disjoint entities are explored in one order only), then `search/workers.py` (a multiprocessing pool). If it's still slow after that, set the default depth to 3.

**Done when:**
- With no hints, `vandal search --scenario a --depth 4` finds R3's 3-step counterexample, minimized.
- It prints the number of sequences explored and the throughput.
- The ms/run number is recorded here: `____ ms/run at depth __`.

---

### R5 — Root cause: authorization coverage · ~2h · P2
**Build:**
- **`synth/coverage.py`:** builds the chain for any payment (obligation → approval → execution → settlement → books) and finds the **first uncovered link**.
  - The trace builder is shared with B5's explanations.
- **The `Diagnosis` model:**
  - gap type: `approval_binding`, `verification_channel`, `execution_idempotency`, `duplicate_obligation`, `aggregate_threshold`, or `refund_destination`;
  - the cited event ids;
  - the violated invariants.

**Done when:** a test shows that for R4's counterexample the diagnosis is `approval_binding`, citing the approval, the change request, and the payment.

**R4 + R5 make milestone M2.**

---

### R6 — Control templates, evidence model, lints · ~4h · P2 (templates, lints) + P1 (gate checks, evidence)
**Build:**
- **P2, `synth/templates.py`:** T1–T6 (DESIGN §9.2) as `Control` models that `compile()` to `Check`s. Plus the policy store: `Policy(version, controls, parent, diff)`.
- **P2, `synth/lint.py`:** three lints:
  - **overfit:** equality on amounts, ids, or invoice numbers;
  - **spoofable:** clears a hold using only fields the attacker can forge;
  - **block-where-hold-works.**
- **P1, `twin/evidence.py`:** the verification evidence model.
  - The new move `inbound_confirmation(channel=phone_in|video, voice_match=0.95)` creates `phone_in` evidence. This is the deepfake case.
  - The reference Operator answers a hold that has a `require` clause with an outbound callback (`contact_as_of` per the control).
  - The simulated callee answers truthfully when the call reaches the real vendor, and confirms falsely when it reaches the attacker.
- **P1:** the gate runs any compiled `Check` generically, including clearing a `require` hold only when the required evidence event exists.

**Done when:**
- With `T1(accepted=[phone_outbound, portal], contact_as_of=before_request)` and `T2(bound=[amount, payee_account])` installed by hand, `vandal search --depth 4` finds **0 violations**.
- A T1 that accepts `phone_in` is rejected by the spoofable lint. Without the lint, search beats it with `inbound_confirmation`.

---

### R7 — Verification suite, evidence pack, scorecard · ~3h · P4
**Build:**
- **`verify/regression.py`:** about 20 legitimate cases, including:
  - a real bank change confirmed by outbound callback;
  - a credit memo with a corrected invoice;
  - a legitimate retry after a real failure.
- **Legitimate-ops replay:** all 80 seeded invoices.
- **`verify/variants.py`:** a parametric content-variant generator (vendor × amount band × channel × sender × follow-up, including `inbound_confirmation`).
- **`verify/evidence_pack.py`:** the `EvidencePack` JSON (counterexample, diagnosis, candidates, chosen control, diff, before/after metrics) and the scorecard numbers.

**Done when:** `vandal verify --policy v1` passes all six checks in DESIGN §10 and writes `evidence/v1.json`. The same command reports the failures under v0.

---

### R8 — CEGIS synthesizer · ~4h · P2 (uses L0)
**Build:**
- **`synth/propose.py`:**
  - Claude (`MODEL_SYNTH`, through `llm.py`) gets the diagnosis, the policy, and the template catalog, and returns candidates as structured output (template + params + rationale).
  - Fallback: an **enumerative parameter sweep** over the templates matched to the gap type.
- **`synth/objective.py`:** `ResidualExposure + λ·LegitBlocked + μ·Holds`.
- **`synth/cegis.py`:** propose → lint → search under `v0+candidate` → regression check from R7 → any counterexample or false positive goes back as feedback. Maximum 4 iterations.
- **The iteration log:** each iteration's candidate, result, counterexample, and score, streamed to the API.

**Done when:**
- Starting from R5's diagnosis, it ends at a control set with no violations within k, 0 legitimate blocks, and **at least one refuted candidate in the log**.
- It works with `--no-llm`.
- Exhausting the iterations gives an honest "cannot auto-repair" result.

**R6 + R7 + R8 make milestone M3. That's the full Red loop.**

---

### R9 — User-authored threats and Red content · ~3h · P3 (with P2 for search seeding)
**Build:**
- **`search/red.py`:** Claude as Red writes the content for moves: emails, deepfake call transcripts, malicious agent messages, injected text.
- **Plain-language inject:** a description is turned into `list[Move]` within the attacker capabilities. The user previews it before it runs.
- **Compose inject:** raw moves plus oracle labels.
- **Search seeding:** the injected threat seeds the search, which explores up to k moves around it.

**Done when:** `vandal inject "the CFO calls from an airport asking for an urgent wire to a new supplier"` runs on a fresh clone, and either reports that the controls held or sends the violation into diagnose → CEGIS.

---

### R10 — Fault injection: Scenario B, retry double-pay · ~2.5h · P2
**Build:**
- **Bank faults:** `timeout`, `drop_ack`, `duplicate_ack`, `delay(n)`, `feed.delay(n)`.
- **The reference Operator's retry policy** as a parameter. In v0, a timeout means retry with no idempotency key.
- **T3 `IdempotentExecution`.**
- The **Vendor Overpayment Receivable** posting.

**Done when:** search finds `submit → drop_ack → retry` causing a double settlement (INV-3), and CEGIS lands on T3.

---

### R11 — Money in: Scenario F, refund scam · ~3h · P1
**Build:**
- **`twin/money_in.py`:** customers, customer invoices, incoming payments, cash application (including partial payments, one deposit covering several invoices, and unidentified deposits sent to suspense), overpayments, and refunds.
- **New moves:** `deposit(cleared|uncleared)`, then `refund_request(dest=new_account)`.
- **T6 `RefundToSource`** and **INV-11**.

**Done when:** search finds the refund scam under v0, and CEGIS lands on T6 with `require_cleared_funds`.

---

### R12 — Persistence and Supabase · ~2.5h · P4
**Build:**
- **`api/db.py`:** SQLAlchemy Core tables (`runs`, `events`, `policies`, `searches`, `syntheses`, `evidence_packs`, `llm_calls`), connected through `DATABASE_URL` (Supabase pooler, or SQLite as the fallback).
- **Batched event writes.**
- **One Postgres migration through the Supabase connector:** RLS on with no policies, and a trigger that rejects UPDATE/DELETE on `events`.

**Done when:**
- A run rebuilt from its persisted events gives the same `state_hash`.
- An `UPDATE events` statement fails on Postgres.
- The app still runs with SQLite.

---

## 5. Cross-cutting slices

### L0 — LLM wrapper · ~2h · P3 (right after R0)
`vandal/llm.py` provides:
- Claude calls through the Anthropic SDK, with structured output into Pydantic models;
- model choice from env (`MODEL_AGENT`, `MODEL_SYNTH`);
- a cache keyed by `(prompt_version, agent, step, sha256(input))`;
- `DEMO_PLAYBACK=true`, which serves answers only from the cache and fails loudly on a miss;
- a timeout that triggers fallback.

**Done when:** a structured call works, a repeated call hits the cache, and playback mode works with no API key.

### A0 — API skeleton and SSE · ~2h · P4 (right after R0)
- A FastAPI app with an in-memory run registry.
- SSE with run, search, and CEGIS progress.
- Routes added per slice as each one lands: `/demo/reset` (R1), `/runs/{id}/operate` and `/state` (R2), `/search` (R4), `/diagnose` and `/runs/{id}/chain/{payment}` (R5), `/verify` and `/metrics` (R7), `/synthesize` and `/policies/{id}/apply` (R8), `/runs/{id}/inject` (R9), `/approvals` (B3), `/explain` (B5).

**Done when:** the frontend can create a run and stream its events against the real backend.

## 6. BLUE — Vandal Guard

Blue's core (the gate, the checks, running controls, and evidence-gated holds) **ships inside R2 and R6**, because Red can't be tested without it. The remaining Blue slices:

| Slice | Owner | Build | Done when |
|---|---|---|---|
| **B2 Authorization chain at runtime** | P1 | `guard/chain.py`: at `pre_execute`, compare the approved instruction with the instruction about to execute and check the account is verified. Run invariants after each step | Under v1, INV-2 is **blocked before execution**, not just detected afterwards |
| **B3 Roles, SoD, approvals** | P3 | `guard/sod.py` role matrix (DESIGN §6.1), the `guard/approvals.py` inbox, INV-10. Policy patches need a human approval | The Operator can't approve anything; `/policies/{id}/apply` needs an inbox approval |
| **B4 Verdict feed** | P4 | Every `Verdict` (facts, fired checks, citations) streamed over SSE | The UI shows a live allow/hold/escalate stream |
| **B5 Cited explanations** | P3 | `guard/explain.py`: the trace builder (shared with R5) collects the evidence; Claude writes the answer from that trace only; citations are validated and regenerated if they don't resolve; pushback never clears a hold | `GET /explain/payment/PAY-…` returns an answer where every claim cites an id that resolves |

## 7. OPERATOR — the agent being protected

| Slice | Owner | Build | Done when |
|---|---|---|---|
| **O0 Reference Operator** | P1 | Deterministic, no LLM (built in R2, extended in R6 and R10) | Covered by R2, R6, R10 |
| **O1 LLM intake** | P3 | `llm_operator.py`: classify channel events, extract fields, match vendor and PO, code the GL, propose an action. Uses the messy-doc fixtures (DESIGN §5.6) | Field and GL accuracy against oracle labels is reported by the scorecard (target: 90% or better) |
| **O2 Exceptions + recovery** | P3 | Holds, outbound callbacks, recall, reinstating liabilities, re-payment requests through the inbox, reconciliation | After Scenario A under v0, the books show the receivable and the reinstated AP, and INV-1 and INV-7 hold |
| **O3 Approvers + money in** | P3 | Chase approvals, handle denials; cash application and refund requests through Blue | A denied invoice goes to `held` with its reason recorded; refunds flow through Blue |

## 8. FRONTEND — war room

**Owner:** P4. F0 starts after R0, against mocks built from the `contracts/` shapes. Each later slice switches to the real API as soon as its backend lands.

| Slice | Build | Backend needed |
|---|---|---|
| **F0** | Next.js + Tailwind scaffold, mock API, three-column dark layout | none |
| **F1** | Twin view: cash, AP, exposure; invoices, payments, ledger, and bank tabs | R2, A0 |
| **F2** | Search panel: live sequence counter, violating traces, minimal counterexample timeline | R4 |
| **F3** | Authorization-chain view with the broken link highlighted | R5 |
| **F4** | CEGIS log, scored candidates, policy diff, before/after | R8 |
| **F5** | Blue verdict feed + approvals inbox (patch approval) | B3, B4 |
| **F6** | Inject form (plain language + compose), scorecard, Reset, playback toggle, Judge view | R9, R7, L0 |

## 9. Milestones

| Milestone | Slices | Target |
|---|---|---|
| **M1** | R0–R3, L0, A0, F0–F1 | Sat 12 PM |
| **M2** | R4–R5, F2–F3, O1 started | Sat 4 PM |
| **M3** | R6–R8, B2–B3, O1, F4 | Sat 9 PM |
| **M4** | R9, B4–B5, O2, F5–F6, R12 | Sun 1 AM |
| **M5** | R10, R11, O3 | Sun 3 AM |

**Fallback checkpoint at Sat 4 PM.** If R4 can't find Scenario A by then, use LLM-guided Red plus R7's held-out variants as the verifier inside CEGIS, and keep going.

**Cut order, if behind:** R11 → O3 → R10 → R12 (stay in memory + SQLite) → B4's live feed (show the log instead). **Never cut:** R0–R9, L0, A0, B2, B3, B5, O1, F1–F5.
