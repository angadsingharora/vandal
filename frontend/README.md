# Vandal war room

The frontend for Vandal (IMPLEMENTATION §8, slices F0–F6). Next.js, Tailwind, dark. The war room has two sides, switched in the top bar:

- **Blue · Vandal Guard** is the live path. The Operator (the finance agent) works the books; Guard checks every tool call it makes and allows, holds, or escalates it; humans decide in the approvals inbox. Panels: the Operator, Guard's verdicts, the books, the enforced policy, and approvals.
- **Red · Vandal Sandbox** is a clone, never the live books. Vandal attacks the twin, diagnoses the broken link, and synthesizes and verifies a fix, which it sends to Blue. Panels: the attack, the verdict (what the books say next to what actually happened), the sandbox twin, the diagnosis chain, and fix & prove.

A strip under the top bar shows the seven steps of the loop, coloured by the side that does each one, with the next thing to click. Click a step to go to its side.

## Run it

Against the backend:

```bash
cd backend && uv run uvicorn vandal.api.main:app --reload      # :8000
cd frontend && npm install && npm run dev                      # :3000
```

Without a backend (the mock API, F0):

```bash
cd frontend && npm run dev:mock
```

Settings (copy `.env.example` to `.env.local`):

| Variable | Default | |
|---|---|---|
| `NEXT_PUBLIC_VANDAL_API` | `http://localhost:8000` | Backend base URL. Its CORS origins come from `VANDAL_CORS_ORIGINS` (default `http://localhost:3000`) |
| `NEXT_PUBLIC_VANDAL_MOCK` | `0` | `1` serves every call from `src/mock`, in the browser |

## The demo loop (DESIGN §13)

1. **Blue · Operate.** **Reset demo** seeds the company under the chosen policy. **Run operations** has the Operator work N business days, with every tool call going through Guard. The verdicts and the books update live.
2. **Red · Attack.** **Unleash Vandal** runs a bounded search over the threat you pick. The sequence counter updates live, the minimal counterexample shows as a timeline, and the verdict card above the twin shows the books balancing while the money went to the wrong account. **Replay on twin** plays it on a fresh clone and opens it as a run tab (switch on **Judge view** to see the attacker's account).
3. **Red · Diagnose** walks the authorization chain and highlights the broken link with the facts Guard evaluated. Click any payment to see its own chain.
4. **Red · Fix.** **Synthesize a control** streams CEGIS: each candidate, the counterexample that beat it, and the scored table.
5. **Red · Prove.** **Verify** runs the six checks at the same depth and shows the before/after scorecard. **Send to Blue for approval** puts the policy and its evidence pack in Blue's inbox and switches to Blue.
6. **Blue · Approve.** Approve it as the Controller (the synthesizer can't approve its own patch), then **Apply** it to Guard.
7. **Blue · Enforce.** **Replay Red's attack under …** in the enforced-policy card runs the same counterexample under the new policy: HELD, $0, beside the original.

Also included:
- **Try your own scenario** describes a threat in plain language, or composes moves and labels by hand. You can preview the plan, run it, and send any violation into diagnose → CEGIS. It runs on a fresh clone under the focused run's policy (the Live tab's, or a replay tab's), which is what its button names.
- Claude reads threats and proposes controls by default whenever the server has a key or playback recordings (`/settings`); tick **no LLM** / **Read it with keywords** to use the deterministic paths instead.
- **Scorecard** compares policies side by side.
- **why?** next to a payment, invoice, or change request opens Blue's cited explanation. Push back and the hold stands.
- **Operator tries to approve** in the inbox shows segregation of duties refusing it.
- **Playback** flips `DEMO_PLAYBACK` on the server: every LLM call is served from the recordings in `backend/llm_cache/`, with no API key and no network. A call with no recording falls back to the caller's deterministic path.

## Layout

```
src/
  app/            Next.js app router: layout, page, theme
  components/     WarRoom (the two sides), TopBar (side switch, loop strip), one file per area
                  (SearchPanel, AttackVerdict, TwinPanel, ChainView, SynthesisPanel, BluePanels,
                  InjectDialog, ScorecardDialog, ExplainDrawer)
  lib/
    types.ts      the backend's shapes (contracts/, api/)
    api.ts        VandalApi: HttpApi (fetch + EventSource) or the mock
    store.ts      zustand store: the demo loop's state and actions
    format.ts     integer cents → dollars, move labels, oracle → account mapping
    loop.ts       the seven loop steps and which one is next
  mock/
    mockApi.ts    the mock API: replays fixtures with the backend's job and SSE semantics
    fixtures.json recorded from the real backend
scripts/
  capture_fixtures.py   re-records fixtures.json
```

Re-record the mock's fixtures after a backend change to the API's shapes:

```bash
cd frontend && uv run --project ../backend python scripts/capture_fixtures.py
```

## Checks

```bash
npm run typecheck
npm test          # lib unit tests (node --test)
npm run build
```
