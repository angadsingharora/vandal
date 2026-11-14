# Vandal backend

## Message hunt

```
uv run vandal hunt-messages --policy v0 --attempts 6 --seed 7
```

Strike's other attacks hand the company messages whose meaning is already settled: a move says
"this is a bank change for V-007", and the Operator acts on it. They never test the step where a
model reads free text and decides what it is. The message hunt (`vandal/search/message_hunt.py`)
tests that step.

- **Attacker.** Claude, playing Red, sees the company as an outsider could: vendors, contacts on
  file, open invoices, when its message lands, the approval threshold, and the active controls.
  It writes one inbound message (channel, sender, subject, body). It is seeded with two messages
  from a live test, one that was caught and one that worked, and it is given its own receiving
  account.
- **Target.** The message is delivered with no structured fields, on a fresh clone, after the
  day's approvals and before the payment run. The Operator's real intake (`operator/intake.py`,
  through Claude) classifies it and extracts its fields, and the LLM Operator turns that into
  at most one tool call. Guard rules on every call as usual, and the twin runs the payment run
  and settles it.
- **Score and feedback.** For each attempt it records what intake read, every Guard verdict on
  calls the message caused, the invariants broken, the money paid to accounts that aren't
  verified, and any case opened. A one-line summary of each attempt goes into the attacker's
  next prompt, so it adapts. For example, once v1 holds its bank changes, it switches to
  invoices with its account inline.
- **Report.** The report gives attempts, hits, attack success rate, total exposure, and the best
  hit. It is printed and written to `hunts/messages-<policy>-seed<n>.json`. Over the API,
  `POST /runs/{id}/hunt-messages` starts the hunt as a job. Its `best` is a one-move
  `inbound_message` trace, so `/diagnose` and `/synthesize` take the job's id.

**How it differs from the others.** `vandal search` enumerates a fixed alphabet of structured
moves per threat family. `vandal hunt` replays a hand-written playbook, also structured, and
calls no model. Both test controls against moves whose meaning is given. The message hunt is
the only one where a model writes the attack and another model's reading decides what the
company does.

**Reproducible.** Both the attacker and intake call Claude through the record-and-replay cache
(`vandal/llm.py`, `llm_cache/`). The same seed and the same recordings give the same report, and
`DEMO_PLAYBACK=true` runs it with no key and no network. The committed recordings cover
`--policy v0` and `--policy v1` at the defaults. Other settings need `ANTHROPIC_API_KEY` once, to
record. `--attempts`, `--max-calls`, and `--max-tokens` cap the spend, and cache hits count
toward the call cap, so a replay stops where the recording did.

**Limits.**

- Results depend on the target model and on intake's prompt. A different model, or a different
  prompt, gives a different success rate.
- The attack success rate is measured in simulation, on the sandbox's fictional company, against
  one Operator. It is not a rate for any real deployment.
- Intake has no notion of a suspicious sender. It reports what a message is, not whether to
  trust it. A lookalike domain that a full agent might flag is read as a bank change like any
  other, so under v0 it pays out, and only a control such as v1's callback stops it.
- `/diagnose` and `/synthesize` replay a hit with the rule-based reader, not the model. For
  bank-change text the two readers agree. A hit that depends on the model misreading something
  might not reproduce there.
- One message per attempt, delivered at one point in the schedule. Multi-message conversations,
  phone calls, and replies to the agent are out of scope.
