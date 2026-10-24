# Nap report

_Written by the overnight session while the owner slept. Updated after every item. Commands are run from `backend/` with `python -m uv run ...` unless noted._

## Summary (five lines)

1. **PRs in merge order (top to bottom, each stacked on the one before):** [#25](https://github.com/angadsingharora/vandal/pull/25) `slice/L0-fixes` → [#26](https://github.com/angadsingharora/vandal/pull/26) `slice/L0-recordings` → [#27](https://github.com/angadsingharora/vandal/pull/27) `slice/demo-e2e` → [#28](https://github.com/angadsingharora/vandal/pull/28) `slice/ui-polish` → [#29](https://github.com/angadsingharora/vandal/pull/29) `slice/R-scenario-c` → [#30](https://github.com/angadsingharora/vandal/pull/30) `slice/partial-handoffs` → [#31](https://github.com/angadsingharora/vandal/pull/31) `slice/submission` → [#32](https://github.com/angadsingharora/vandal/pull/32) `slice/ci`. Nothing was merged by this session.
2. **Tests before:** fast suite 1 failure on `main` (the stale war-room test). **After, on the top of the stack:** fast suite green, `--slow` green including the new end-to-end smoke test, ruff clean, `npm run typecheck` / `npm test` / `npm run build` green. Playback proof: the whole CLI loop with no key and `DEMO_PLAYBACK=true`, **0 cache misses**.
3. **Look at this first:** `python scripts/demo.py --playback` and click the loop (README, "Run the whole demo with one command"); then section 2's finding (structured output can't fill a free-form dict, so every LLM inject and every LLM-proposed control was silently empty before PR 26) and section 3's two demo-killers (inject ran on the wrong run; a second loop in one server crashed Verify).
4. **Broken / open:** `vandal synth --scenario f` cannot auto-repair at depth 3 (passes at depth 2; not in the demo script); Scenario D and "sources that disagree" are not built (over the two-hour line, written up in section 4); a held invoice is not re-validated when its receipt arrives later.
5. **Needs the owner:** review and merge the stack; make the repo public or add the judges; record the video opening on the one-move counterexample; paste `docs/DEVPOST.md`; do one Reset on the demo server before judges arrive (the first Reset after a long session takes about 2 s, the next ones 30 ms).

## Where the work happened

The checkout `C:\Users\Angad\vandal` was being edited by another session (O1 API and intake panel, uncommitted) when this run started, so this session worked in a git worktree at `C:\Users\Angad\vandal-nap` on the same repository. Every branch and PR is in the shared remote; the worktree can be removed with `git worktree remove C:\Users\Angad\vandal-nap` once the stack is merged. `backend/.env` was copied into the worktree, never printed.

## 1. L0 and the failing test — `slice/L0-fixes`

**Already done before this run:** PR 23 (`slice/L0-llm`, merged) landed the Claude wrapper, and 24 intake recordings were committed with it. So this slice holds only what the brief's step 1 still needed.

- **Stale test fixed.** `tests/test_api_war_room.py::test_entities_show_the_misdirected_payment_and_the_answer_key` expected the attacker's account to be `unverified`. Since PR 20 (O2) the replay's remaining days run the Operator's recovery, which marks the payment `misdirected`, reinstates AP (DESIGN §12), and rejects the bad payee. The recovery is the designed behaviour, so the test now asserts `rejected` and `misdirected`, with the reason in a comment.
- **Live check:** `VANDAL_LIVE_LLM=1 python -m uv run pytest tests/test_llm.py` → 7 passed. The key and the SDK call shape (`betas`, `fallbacks`, `output_config`) work with `anthropic` 2.3.0. No change needed.
- **Playback fallback per caller:** new `tests/test_playback_fallback.py` sets `DEMO_PLAYBACK=true` with no key and an empty cache, and checks that intake, Red's plan and content, the CEGIS proposer, and Blue's explanation each take their deterministic path and record a `playback` note.
- **READMEs:** the "until L0 lands" lines in `README.md` and `frontend/README.md` now describe the cache and playback as they are.

See it: `python -m uv run pytest` (fast), `python -m uv run pytest --slow`, `python -m uv run ruff check .`; `cd frontend && npm run typecheck && npm test && npm run build`.

## 2. Recordings and playback — `slice/L0-recordings`

**Found while recording, fixed here:** Red's plain-language reader and the CEGIS proposer asked Claude for a free-form `dict` of parameters. Claude's structured output can't fill an open dict, so every move and every candidate came back with `params: {}` and the model wrote the parameters into its notes instead ("the output schema only accepts empty params objects"). Every LLM inject then failed with "nothing in this threat is within the attacker's capabilities", and the LLM synth proposed only default-parameter controls (three identical T3s for Scenario B, which then "cannot auto-repair"). Fix: `_LLMMove.params` and `_LLMCandidate.params` are lists of `{key, value}` pairs folded into the dict in code; prompt versions bumped to `red-v2` and `synth-v2`; duplicate candidates within one iteration are dropped. Intake and explanations were never affected (flat schemas).

**What was recorded with the real key** (`backend/llm_cache/`, committed):
- `vandal intake`: 24 messy items, all through Claude. **LLM intake: 120/120 fields, 24/24 GL codes**, the same as the deterministic reader. Cost: 24 calls (recorded by PR 23's author; this run served them from cache).
- `vandal run --days 5 --operator llm`: zero LLM calls. Structured events take the reference path by design (IMPLEMENTATION §0), so this command records nothing.
- `vandal synth --scenario a` (from v0), `b` (from v1), `f` (from v2): the proposer's calls per iteration. Scenario B from v0 can't pass regression (the suite's bank-change cases need v1's T1), so b and f start from the policy that precedes them, as `backend/policies/` stacks them.
- `vandal inject` with three threats: the Scenario C shape (cloned-voice callback after a bank change), the Scenario E shape (counterparty agent waives callbacks, asks for other vendors' remittance details), and the CFO airport call.
- `GET /explain/...` for PAY-0057, INV-1042, CR-0001, and a pushback question, through the API after reset → run → replay Scenario A.

**Keys are content-only:** `tests/test_llm_cache.py` recomputes each file's key from its stored request and checks it matches the file name, validates every response against the caller's schema, and greps for secrets. A prompt with a run id or wall-clock timestamp fails the test.

**Two more crashes fixed in the same slice.** With real parameters, the model sometimes plans a `submit_invoice` move. (1) The twin's attacker-invoice stub raised `NotImplementedError` straight through `vandal inject`; Red's capability filter now drops such a move with a "not modeled" note. (2) A `submit_invoice` without `number`/`amount` was a `KeyError`; it is now an `IllegalMove` like every other half-specified move.

**Known limit found, not fixed (owner, look at this):** `vandal synth --scenario f --policy v2` **cannot auto-repair at the default depth 3**, with the sweep or the LLM. Every T6 variant is beaten by `deposit@3; deposit@3; refund_request@4 → INV-4`: two deposits followed by a refund. The R11 test (`tests/test_money_in.py::test_cegis_lands_on_t6_with_cleared_funds`) runs at depth 2, where T6 survives. Either INV-4 counts a refund of an attacker's own cleared second deposit as a loss (a false positive in the oracle), or T6 needs a parameter the template library lacks. Reproduce: `python -m uv run vandal synth --scenario f --policy v2 --no-llm` (and `--depth 2` to see it pass). The demo script (DESIGN §13) uses Scenarios A and B only, so the demo is not affected.

**Server-side fallback shows up in the cache.** Two Red content calls were answered by a different model than requested (the `server-side-fallback` beta the wrapper opts into). The cache entry stored the answering model as `request.model`, so the key could not be recomputed from the entry. Entries now store the requested model (what the key is made of) plus `served_by`; the two old entries were rewritten the same way.

**Playback proof:** with `DEMO_PLAYBACK=true`, `VANDAL_DOTENV=0` (so no key at all), the whole CLI loop (`intake`, `run --operator llm`, `synth a/b/f`, three `inject`s with repair, the four `/explain` calls) completed with **0** `playback: no recording` / `LLM unavailable` lines. Script: the loop in section 2 above; the war room's clicks were recorded through the API on port 8010 during section 3 and are in the same cache. The three `inject`s and `synth f` exit 1 by design (a violation was found / cannot auto-repair), not from a miss.

**Cache inventory (committed):** 24 intake, 4 Red plans, 4 Red content, 5+2 synth proposals (iterations 1 and 2), 5 Blue explanations. `grep -r sk-ant backend/llm_cache` → nothing.

## 3. The demo loop in the war room — `slice/demo-e2e`

Driven in the browser against the worktree's API (`:8010`) and `next dev` (`:3010`), with the real key so every click's LLM call was recorded. Screenshots of each panel are in `docs/screenshots/` (taken at 1440×900; the overnight pane scales them, so the polish slice retakes them full size).

Every step of DESIGN §13 ran: Reset → Run operations (80 paid, all invariants hold) → Unleash Vandal (65 sequences, 12 violating, 1-move counterexample, $40,000) → Replay on twin (Attack tab, exposure $40k, 3 broken) → Diagnose (execution link broken, `approval_binding`) → Synthesize with Claude (T2 refuted twice, T2+T1 survived, lint caught T1-with-video) → Verify (6/6, approvable) → Submit → Approve as Controller → Apply → Replay under v1-synth (HELD, $0) → inject a never-seen threat (Claude's plan: lookalike bank-change email for Summit Roofing plus a pressure email, with written content) → why? on PAY-0057 (Claude, every claim cited) → push back ("the hold stands") → Scorecard (v0 $300,787 exposure vs v1-synth $0; intake 100%/100%; 0 legit blocked) → Judge view → Playback toggle (server flag flipped, confirmed on `/settings`).

**Bugs found and fixed:**
- **Inject ran on the wrong run.** The dialog's button says "Run on <focused run's policy>" (e.g. `v1-synth` from the replay tab) but the store always posted to the Live run (v0). So the judge's threat appeared to break `v1-synth` ($9,461.68 to a lookalike) when the API under `v1-synth` actually holds it. `previewInject`/`runInject` now use the focused run, so the label and the policy agree.
- (backend, in slice 2) the two inject crashes above, found by driving this form with Claude's reader.

**Not reproducible in the UI, covered by the smoke test instead:** "Operator tries to approve" is offered only on pending *payment* approval requests, and the simulated approver clears those within the day, so a 5-day run leaves none pending. Segregation of duties for policy patches is asserted in `scripts/demo_smoke.py` (403 for the Operator).

**UI polish items noted for slice 3b:** Escape does not close the explanation drawer or the scorecard; the right column's Operator/verdict rows extend past 1440 px (long verdict text has no `min-w-0`); the search panel keeps "12 violating traces" from the v0 search after a replay tab under v1-synth is focused; the Scorecard's per-class rows render `0/0` in red/green with no legend.

**Demo-killer found by the smoke script, fixed:** with `DATABASE_URL` set (the default `.env` has SQLite), running the loop a second time in the same server process failed at Verify with `UNIQUE constraint failed: evidence_packs.id`, because `save_evidence_pack` and `save_policy` inserted rows keyed by the policy version (`v1-synth`). A judge pressing Reset and running the loop again would have hit it. Both saves now replace the row for that version (`tests/test_persistence.py::test_saving_the_same_version_twice_replaces_it`).

**Reset timing:** 32 ms for a Reset on a warm server; the first Reset after a long session with many runs and SQLite persistence took 2.2 s (dropping runs and flushing event batches). `scripts/demo_smoke.py` reports both and asserts the warm one is under 1 s. Before the demo, do one Reset before the judges arrive.

**`backend/scripts/demo_smoke.py`** drives the whole loop over HTTP (`--base-url`, default `:8000`) or in process (`--in-process`), with Claude or `--no-llm`, and asserts the key numbers: $40,000 under v0, HELD and $0 under the synthesized policy, 0 legitimate payments blocked, every scorecard field non-null, the Operator refused on the patch (403), Blue's claims all cited, the pushback leaves the hold. `tests/test_demo_smoke.py` runs it in process on the deterministic paths as a slow test. Against the live server with Claude (answers from the cache):

| step | time |
|---|---|
| Reset (warm) | 32 ms |
| Run operations, 5 days | 0.2 s |
| Search, depth 2 | 0.9 s |
| Replay, diagnose | 0.1 s each |
| Synthesize (CEGIS, depth 2, Claude) | 47 s |
| Verify (depth 2) | 25 s |
| Inject (never-seen threat, depth 2) | 0.8 s |
| why? + pushback | 20 ms (cached) |
| Scorecard (depth 1) | 14 s |

Run it: `cd backend && python -m uv run python scripts/demo_smoke.py` with the API on `:8000`, or `--in-process`.

**Mock fixtures re-recorded** (`frontend/src/mock/fixtures.json`, 605 KiB) from the API after the O1/L0 shape changes, with `cd frontend && python -m uv run --project ../backend python scripts/capture_fixtures.py`. `npm run dev:mock` shows the same loop offline with no backend at all. The mock's synthesis and verify fixtures come from the deterministic sweep (`no_llm: true` in the capture script), so the mock never needs the cache.

## 3b. War-room polish — `slice/ui-polish`

No backend changes. Walked every panel at 1440×900 and 1024×768 against the real API and the mock.

- **Keyboard and focus:** one `:focus-visible` ring for every control (filters, tabs, why?, table rows had none); Escape closes the explanation drawer, which now focuses its question box when it opens (the Modal already handled Escape).
- **Claude by default** when the server reports a key or playback: the Synthesis panel's "no LLM" and the inject dialog's "read with keywords" start unticked in that case, so the demo shows Claude without a click; both still toggle.
- **Scorecard:** the per-class rows are introduced by a legend ("attacks that got through, by threat class · succeeded / attempted") and a class with no attempts shows "—" in grey instead of a green `0/0`.
- **Search panel:** the "N violating traces at this depth" fold belongs to the last search; it no longer shows under a counterexample that came from the inject form.
- **Layout:** every grid column and panel has `min-w-0`, so long verdict and case lines shrink inside their column instead of pushing it wider. With a diagnosis open, the authorization chain used to take the whole middle column at 1440×900 and the payments table collapsed to zero rows (its why? buttons unreachable); the chain now caps at 46% of the viewport and scrolls, and the twin keeps at least 260 px.
- **Inbox:** one row per policy version (the newest); a second loop in one server used to list `v1-synth` twice.
- **Captions on jargon:** the CEGIS heading and each verification check name carry a one-line tooltip (DESIGN §9.3, §10); invariants already had theirs.
- `frontend/README.md` says what the inject button targets and when Claude is used.

Before/after pairs in `docs/screenshots/`: `03-replay-diagnose-chain.jpg` → `after-03-chain-and-twin.jpg` (the twin's rows stay visible under an open diagnosis), `09-explain-why.jpg` → `after-09-explain-why.jpg`, `11-scorecard.jpg` → `after-11-scorecard.jpg` (per-class legend, neutral empties).

## 4. DESIGN §5.6 / §11 gaps

Done smallest first, as the brief says. Two items landed; two were judged over the two-hour line and are written up below instead.

### Scenario C as a first-class held-out variant — `slice/R-scenario-c`
- The held-out grid (`verify/variants.py`) already carried both deepfake classes (`deepfake_phone`, `deepfake_video`: an inbound confirmation at voice match 95 after a bank change) for every vendor, timing, channel and sender, so Verify's "0 of 40 held-out variants succeeded" already included them.
- What was missing was a trace of its own and a test that pins the story the demo tells at 2:10. `scenarios/c_deepfake.json` is Scenario A plus the cloned-voice confirmation; `tests/test_scenario_c.py` replays it: under v0 the money goes (INV-4, INV-5, $40,000); under v1 the inbound call is not a verification channel and the change is held; a T1 that accepts inbound calls (`policies/t1_phone_in.json`) is beaten by the same moves placed before approval, and the spoofable lint rejects that T1. The README's scenario table has a row for it.
- In the war room, the inject example "a vendor emails new bank details after approval, then calls to confirm" is this scenario; run it from the `v1-synth` replay tab to show "deepfake confirmation variant → still held" (the inject target fix in slice 3 is what makes that work).

### Partial handoffs — `slice/partial-handoffs`
- **An invoice before its receipt** already held cleanly: the v0 3-way match fires `v0.match.missing` with `match.status = no_receipt`, the invoice goes to `held`, no payment is built, every invariant holds, and the other 79 invoices are paid. `tests/test_partial_handoffs.py` pins that.
- **A bank change with no account number** used to be dropped silently by the LLM Operator (intake read `vendor_bank_change` for V-007 with `routing = account = None`, and nothing happened, nothing recorded). It now opens an `exception` case through Blue ("bank change request from V-007 without routing and account number; nothing applied, details to be requested through a verified channel"); no change request is created, the vendor's verified account stands, and the company runs on. The reference path never sees this (a `change_request` move always carries an account; the tool itself refuses one without).
- Not done: a held invoice is not re-validated when its receipt arrives later. `invoices.validate` moves `received → validated`, and the Operator only validates `received` invoices, so a late receipt leaves the invoice `held` for a person. Worth an Operator step (`_intake` re-validating held invoices whose match now passes) if the receipt-arrival move is added with Scenario D.

### Skipped, over two hours each (owner, decide)
- **Sources that disagree** (`slice/O1-conflicts`): four planted discrepancies each need a twin change (contract rates on vendors, wire fees on the feed, phone on the contact history, a late feed line), a `Truth` label, an Operator check that notices, and the scorecard's "planted discrepancies caught" to become a number. The scorecard still says "n/a" in its notes.
- **Scenario D** (`slice/R-scenario-d`): `verify/replay.py` still raises `NotImplementedError("attacker invoice variants land with Scenario D")`. It needs the attacker `submit_invoice` moves (`split_2x` under the threshold, `INV-1042-A`), their oracle labels, an INV-3/INV-6 story the search finds at depth ≤ 4 in a new scenario window, and CEGIS closing it with T4/T5 (the templates exist and compile). Red's LLM reader already proposes `submit_invoice` moves for invoice threats and drops them with a "not modeled" note until this lands.

## 5. Submission checklist (DESIGN §20) — `slice/submission`

- **Secrets in git history:** `git log -p --all | grep -nE "sk-ant-|postgresql\+psycopg://[^ ]*:[^ ]*@"` finds nothing but the regex in `tests/test_llm_cache.py` itself. Nothing to rotate. (`backend/.env` is ignored and was never printed.)
- **One command for the whole demo:** `python scripts/demo.py --playback` starts the API on `:8000` and the war room on `:3000` (first run does `npm install`), with every Claude call served from `backend/llm_cache/`. `--mock` runs the war room alone from fixtures; without flags it calls Claude live. Tried on spare ports in playback: both answer, `/settings` reports `playback: true`.
- **README:** the one-command run and the judge's click order; the scorecard table from an actual run (the smoke run's `/metrics`, plus the depth-3 verification numbers); the real-vs-simulated table (DESIGN §10.2); the can/can't-claim table (§18); the Scenario C row. "Proof" wording: the README already said "not a proof"; the bounded-claims line now says "verified by replay and re-search".
- **`docs/DEVPOST.md`:** the seats line, the Red / Blue / Operator split, the self-healing loop, real vs simulated, the scorecard, a 3:00 demo script with timestamps drawn from DESIGN §13 and what the war room actually shows, how it was built, what's next.
- **Still for the owner:** make the repo public or add the judges (DESIGN §20's first box); record the video so it opens with the one-move counterexample; the Devpost text is ready to paste.

## 6. Extras

- **CI** (`slice/ci`): `.github/workflows/ci.yml` runs the fast suite, `ruff check`, `ruff format --check`, `npm run typecheck`, `npm test`, and `npm run build` on every PR and on pushes to `main`. Not run here (no Actions locally); the first PR after merge shows it.
- **Search under 60 s at exhaustive depth 4:** not attempted. The machine ran the slow suite, the recordings, and the smoke runs back to back all night, so a profile would not have been representative, and the demo uses depth 3 (R4's documented default). `backend/scripts/bench_twin.py` is where to start.

## Stack, as opened

| # | branch | base | PR |
|---|---|---|---|
| 1 | `slice/L0-fixes` | `main` | #25 |
| 2 | `slice/L0-recordings` | `slice/L0-fixes` | #26 |
| 3 | `slice/demo-e2e` | `slice/L0-recordings` | #27 |
| 4 | `slice/ui-polish` | `slice/demo-e2e` | #28 |
| 5 | `slice/R-scenario-c` | `slice/ui-polish` | #29 |
| 6 | `slice/partial-handoffs` | `slice/R-scenario-c` | #30 |
| 7 | `slice/submission` | `slice/partial-handoffs` | #31 |
| 8 | `slice/ci` | `slice/submission` | #32 |

Merge top to bottom; after each merge GitHub retargets the next PR to `main`. The worktree at `C:/Users/Angad/vandal-nap` can be removed once the stack is merged (`git worktree remove C:/Users/Angad/vandal-nap`); its only untracked files are a copy of `NAP_PROMPT.md` and `.claude/launch.json`. One more Blue explanation recorded by the smoke runs is committed with this slice.
