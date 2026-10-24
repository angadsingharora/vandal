# Vandal war room

The frontend for Vandal (IMPLEMENTATION §8, slices F0–F6). Next.js, Tailwind, dark. It follows DESIGN §14: Red's search on the left; the twin and its authorization chains in the middle; the Operator, Blue's verdict feed, and the approvals inbox on the right; synthesis along the bottom.

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

1. **Reset demo** seeds the company under the chosen policy. **Run operations** has the Operator work N business days, with every tool call going through Blue's gate. The verdict feed and the twin update live.
2. **Unleash Vandal** runs a bounded search. The sequence counter updates live, and the minimal counterexample shows as a timeline with its exposure and the invariants it broke.
3. **Replay on twin** plays the counterexample on a fresh clone and opens it as a run tab. You can see the payment, the attacker's account (switch on **Judge view**), and the books.
4. **Diagnose** walks the authorization chain and highlights the broken link with the facts Blue evaluated. Click any payment to see its own chain.
5. **Synthesize a control** streams CEGIS: each candidate, the counterexample that beat it, and the scored table. **Verify** runs the six checks at the same depth and shows the before/after scorecard.
6. **Submit for approval** puts the policy and its evidence pack in the inbox. Approve it as the Controller (the synthesizer can't approve its own patch), then **Apply** it to Blue.
7. **Replay under …** runs the same counterexample under the new policy: HELD, $0, beside the original.

Also included:
- **Try your own scenario** describes a threat in plain language, or composes moves and labels by hand. You can preview the plan, run it, and send any violation into diagnose → CEGIS.
- **Scorecard** compares policies side by side.
- **why?** next to a payment, invoice, or change request opens Blue's cited explanation. Push back and the hold stands.
- **Operator tries to approve** in the inbox shows segregation of duties refusing it.
- **Playback** flips `DEMO_PLAYBACK` on the server: every LLM call is served from the recordings in `backend/llm_cache/`, with no API key and no network. A call with no recording falls back to the caller's deterministic path.

## Layout

```
src/
  app/            Next.js app router: layout, page, theme
  components/     one file per war-room area (TopBar, SearchPanel, TwinPanel, ChainView,
                  BluePanels, SynthesisPanel, InjectDialog, ScorecardDialog, ExplainDrawer)
  lib/
    types.ts      the backend's shapes (contracts/, api/)
    api.ts        VandalApi: HttpApi (fetch + EventSource) or the mock
    store.ts      zustand store: the demo loop's state and actions
    format.ts     integer cents → dollars, move labels, oracle → account mapping
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
