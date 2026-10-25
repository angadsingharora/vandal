# Vandal war room

The frontend for Vandal (IMPLEMENTATION §8, slices F0–F6). Next.js, Tailwind, dark. The war room is one page per step of the loop, seven in all, on two sides:

- **Blue · Vandal Guard** is the live path: Operate, Approve, Enforce. The Operator (the finance agent) works the books; Guard checks every tool call it makes and allows, holds, or escalates it; humans decide.
- **Red · Vandal Sandbox** is a clone, never the live books: Attack, Diagnose, Fix, Prove. Vandal attacks the twin, names the broken link, synthesizes and verifies a fix, and sends it to Blue.

The stepper under the top bar is the navigation. The page being looked at is outlined; the step to do next breathes until it is done. Every page ends in a footer with one way forward, which also breathes once the page's work is done, and new information rises in with a brief glow. The side switch opens that side's current page.

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

1. **Blue · Operate.** **Reset demo** seeds the company under the chosen policy. **Run operations** has the Operator work N business days, with every tool call going through Guard. The Operator and the books sit in the left column, Guard's verdicts in the middle, the policy and the inbox on the right; all of it updates live.
2. **Red · Attack.** One column, top to bottom. **Unleash Vandal** runs a bounded search over the threat you pick; the result reads as a metric (53 / 65 sequences safe, 12 broke the books), the shortest sequence that broke them shows as a timeline with the money misdirected, and the attack is replayed on a fresh clone right away so the evidence can follow: the message the agent received, with its tells marked, beside each tell checked against the clone's own records (switch on **Judge view** for the answer key). **Diagnose →** carries it on.
3. **Red · Diagnose** names the root cause first, then walks the authorization chain and highlights the broken link with the facts Guard evaluated. **Synthesize a control →** starts CEGIS.
4. **Red · Fix.** The control that survived is spelled out in full, every rule with its parameters (T2 + T1, say), with the policy diff beside it; the candidates it beat and their scores sit below. **Verify →** proves it.
5. **Red · Prove.** The verdict (approvable or not), then the six checks with what each one proves, then the before/after scorecard. **Send to Blue for approval →** puts the policy and its evidence pack in Blue's inbox and opens Blue's Approve page.
6. **Blue · Approve.** The fix from Red with its rule and evidence. Approve it as the Controller (the synthesizer can't approve its own patch), then **Apply** it to Guard, which opens Enforce.
7. **Blue · Enforce.** **Replay Red's attack under …** runs the same counterexample on a fresh clone under the new policy: HELD, $0.00 moved, beside the original, with every verdict Guard gave on the replay.

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
  components/     WarRoom (routes the stage to its page), TopBar (side switch, the stepper),
                  Stage (page frame: header, body, the one-way-forward footer), one file per page
                  (OperatePage, AttackPage, DiagnosePage, FixPage, ProvePage, ApprovePage,
                  EnforcePage) and their parts (EvidenceScan, ChainView, TwinPanel, BluePanels,
                  SearchPanel, synth, InjectDialog, ScorecardDialog, ExplainDrawer, ui)
  lib/
    types.ts      the backend's shapes (contracts/, api/)
    api.ts        VandalApi: HttpApi (fetch + EventSource) or the mock
    store.ts      zustand store: the demo loop's state and actions
    format.ts     integer cents → dollars, move labels, oracle → account mapping
    loop.ts       the seven loop steps (each a page), which one is next, and where a side lands
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
