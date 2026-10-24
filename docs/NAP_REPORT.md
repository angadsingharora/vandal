# Nap report

_Written by the overnight session while the owner slept. Updated after every item. Commands are run from `backend/` with `python -m uv run ...` unless noted._

## Summary (five lines)

1. **PRs in merge order:** (filled in as each opens) `slice/L0-fixes` → ...
2. **Tests before:** fast suite 1 failure (`test_api_war_room.py`, stale since O2). **After:** see each slice below.
3. **Look at this first:** the stacked PR list below, then `docs/screenshots/` once slice 3 lands.
4. **Broken:** nothing known yet.
5. **Needs the owner:** review and merge the stack top to bottom. Nothing was merged by this session.

## Where the work happened

The checkout `C:\Users\Angad\vandal` was being edited by another session (O1 API and intake panel, uncommitted) when this run started, so this session worked in a git worktree at `C:\Users\Angad\vandal-nap` on the same repository. Every branch and PR is in the shared remote; the worktree can be removed with `git worktree remove C:\Users\Angad\vandal-nap` once the stack is merged. `backend/.env` was copied into the worktree, never printed.

## 1. L0 and the failing test — `slice/L0-fixes`

**Already done before this run:** PR 23 (`slice/L0-llm`, merged) landed the Claude wrapper, and 24 intake recordings were committed with it. So this slice holds only what the brief's step 1 still needed.

- **Stale test fixed.** `tests/test_api_war_room.py::test_entities_show_the_misdirected_payment_and_the_answer_key` expected the attacker's account to be `unverified`. Since PR 20 (O2) the replay's remaining days run the Operator's recovery, which marks the payment `misdirected`, reinstates AP (DESIGN §12), and rejects the bad payee. The recovery is the designed behaviour, so the test now asserts `rejected` and `misdirected`, with the reason in a comment.
- **Live check:** `VANDAL_LIVE_LLM=1 python -m uv run pytest tests/test_llm.py` → 7 passed. The key and the SDK call shape (`betas`, `fallbacks`, `output_config`) work with `anthropic` 2.3.0. No change needed.
- **Playback fallback per caller:** new `tests/test_playback_fallback.py` sets `DEMO_PLAYBACK=true` with no key and an empty cache, and checks that intake, Red's plan and content, the CEGIS proposer, and Blue's explanation each take their deterministic path and record a `playback` note.
- **READMEs:** the "until L0 lands" lines in `README.md` and `frontend/README.md` now describe the cache and playback as they are.

See it: `python -m uv run pytest` (fast), `python -m uv run pytest --slow`, `python -m uv run ruff check .`; `cd frontend && npm run typecheck && npm test && npm run build`.
