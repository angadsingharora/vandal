# Vandal war room

The frontend for Vandal (IMPLEMENTATION §8, slices F0–F6). Next.js, Tailwind, dark: black, white, and two voices — red for Vandal, blue for Guard. Two facing pages; the focused one is wide, the other folds to a margin.

- **Red · Sandbox** (left) opens on the terminal: pick a threat and a depth, run Vandal, and read the result left to right as four columns — *Sequence* (the moves, each stamped valid), *Breakpoint* (the one move where an invariant flipped: the document line, approved vs executed, every id openable), *Rule* (the control as installed, its diff, who signed it), *Proof* (replay, re-search, held-out variants, regression, the enforce replay, "why was this held?") — with the verdict sentence under them. Below: the system map, the intercepted evidence, the diagnosis chain, the twin's books, and the full CEGIS log.
- **Blue · Guard** (right) is the live path. The Operator works the books; Guard checks every tool call and allows, holds, or escalates it; humans decide in the approvals inbox. Panels: the Operator, Guard's verdicts, the books, the enforced policy, and approvals.

Across the bottom, the exchange band draws how the two agents interact: Vandal's lane in red, Guard's in blue, the seven loop steps on their owner's lane, and the thread crossing exactly twice — a copy of the books going down into the sandbox, the proven rule coming back up. Click a step to open its side.

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
  components/     WarRoom (two facing pages + margins), TopBar (masthead; useLoop), BreakAndRule
                  (Red's terminal: threat controls, four columns — Sequence, Breakpoint, Rule,
                  Proof — and the sentence), SystemMap (how the three talk, pulses follow the
                  live run), ExchangeBand (the red/blue thread at the bottom), EvidenceScan,
                  one file per
                  area (TwinPanel, ChainView, SynthesisPanel, BluePanels, InjectDialog,
                  ScorecardDialog, ExplainDrawer; SearchPanel's pieces live on in MovesTimeline)
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
