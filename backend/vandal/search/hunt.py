"""Red's threat hunter: a demo of attacks beyond the preset search, run against the twin.

Bounded search (bfs.py) enumerates a fixed alphabet per threat family. The hunter plays the
other role in the demo: it "studies" the company, then tries attacks drawn from a bank of
hypotheses written in advance (PLAYBOOK), one per attempt, in the playbook's order. Nothing here
calls a model: the pause before each attempt is for the audience, and the hypothesis text is canned.

What stays real:
- The twin executes the moves, the gate decides, the invariants judge. Whether an attempt
  breaks anything, how much is exposed, and what Guard held all come from the simulation.
- Oracle labels come from what the moves do (an attacker account is labeled when the attacker
  creates it; a bill Red sends is booked as a duplicate of the vendor's real one, see
  red_bills), never from the hypothesis.
- A move the twin can't execute is dropped with the reason, never faked.
- A hit is minimized like any counterexample, so /diagnose and /synthesize take it.
- Novelty is measured, not asserted: a finding is "outside the preset search" when some move in
  the minimized trace isn't in any threat family's alphabet.

Everything here is about the sandbox's fictional company.
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents, OracleLabel
from vandal.contracts.moves import Move
from vandal.search.alphabet import SCENARIOS, build_alphabet
from vandal.search.minimize import minimize_trace
from vandal.search.red import ThreatPlan, dress
from vandal.twin import money_in
from vandal.twin.state import State
from vandal.verify.replay import IllegalMove, SandboxFactory, replay, replay_detailed

OPEN = ("received", "validated", "approved", "scheduled")
PAUSE_ENV = "VANDAL_HUNT_PAUSE"  # seconds of "thinking" before each attempt
DEFAULT_PAUSE = 3.0


class Hypothesis(BaseModel):
    """One pre-written attack: the story the hunter tells, and the moves the twin runs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rationale: str  # 2-4 sentences for the reviewer: what in the data it targets, and why
    weak_spot: str  # one line: the gap it goes after
    target_invariant: str  # the INV-n it expects to break
    moves: tuple[Move, ...]


def _bank_change(at: int = 2) -> Move:
    return Move(
        kind="change_request",
        at=at,
        params={"vendor": "V-007", "fields": "bank", "channel": "email", "sender": "lookalike"},
    )


# The bank of hypotheses, written against the seeded Bayline books (seed 7), in the order the
# hunt tries them: the demo's story (the bank change after approval, which leads to the T1 and
# T2 fix) comes first. Each breaks v0 in the twin; whether it still does under a later policy
# is for the twin to say.
PLAYBOOK: tuple[Hypothesis, ...] = (
    Hypothesis(
        weak_spot="approval reads the vendor's current account, not the approved one",
        target_invariant="INV-2",
        rationale=(
            "Harbor Point Construction has a $40,000 invoice approved for today's run, the "
            "largest open item in the books. Approval happened against the verified account, "
            "but v0 builds the payment instruction from whatever account is on file when the "
            "batch runs. A bank-change email from a lookalike domain in the gap between "
            "approval and the batch should redirect the whole payment."
        ),
        moves=(_bank_change(), Move(kind="trigger_batch", at=2, params={})),
    ),
    Hypothesis(
        weak_spot="an inbound call counts as verification of a bank change",
        target_invariant="INV-5",
        rationale=(
            "The same $40,000 Harbor Point payment, with cover: after the lookalike email asks "
            "for new bank details, someone with the vendor contact's cloned voice calls in to "
            "confirm them. If a call the attacker places is treated as a verification channel, "
            "the change looks legitimate and the batch pays the new account."
        ),
        moves=(
            _bank_change(),
            Move(
                kind="inbound_confirmation",
                at=2,
                params={"vendor": "V-007", "channel": "phone_in", "voice_match": 95},
            ),
            Move(kind="trigger_batch", at=2, params={}),
        ),
    ),
    Hypothesis(
        weak_spot="a retry after a lost acknowledgement is a second payment",
        target_invariant="INV-3",
        rationale=(
            "Payments go to the bank without an idempotency key under v0, and the Operator "
            "retries anything the bank hasn't acknowledged. If the bank processes the Harbor "
            "Point payment but the acknowledgement is lost, the retry settles the same "
            "$40,000 obligation twice."
        ),
        moves=(Move(kind="fault", at=2, params={"kind": "drop_ack"}),),
    ),
    Hypothesis(
        weak_spot="a near-duplicate bill for a vendor with no PO is matched as new",
        target_invariant="INV-3",
        rationale=(
            "Morrow Electric's open invoice MOR14-1722 ($7,497) carries no purchase order, so "
            "the three-way match has nothing to anchor on. A second bill from the vendor's own "
            "mailbox with the number MOR14-1722B and the same amount should be received, "
            "approved, and paid as if it were a new obligation."
        ),
        moves=(
            Move(
                kind="submit_invoice",
                at=0,
                params={
                    "vendor": "V-014",
                    "number": "MOR14-1722B",
                    "amount": 749_700,
                    "due_in_days": 2,
                },
            ),
        ),
    ),
    Hypothesis(
        weak_spot="an overpayment can be refunded to an account the tenant never used",
        target_invariant="INV-11",
        rationale=(
            "Tenant C-004 owes the most rent, so a deposit from the attacker marked as that "
            "tenant's overpayment lands as credit on its account. A refund request for the "
            "excess, pointing at a new bank account, turns someone else's deposit into a "
            "payout to the attacker if refunds aren't pinned to the source account."
        ),
        moves=(
            Move(
                kind="deposit",
                at=3,
                params={"customer": "C-004", "amount": "overpay", "party": "attacker"},
            ),
            Move(
                kind="refund_request",
                at=4,
                params={"customer": "C-004", "party": "attacker", "dest": "new"},
            ),
        ),
    ),
)


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    violated: list[str]
    exposure: Cents
    violations: list[str]  # the invariant messages
    guard: list[str]  # what Guard held, escalated, or blocked, and which checks fired
    money: list[str] = []  # where money went that the seed didn't already send: refunds, repoints
    dropped: list[str]  # moves the twin couldn't execute, and why


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    rationale: str
    weak_spot: str
    target_invariant: str
    moves: list[Move]
    outcome: Outcome


class Hit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moves: list[Move]  # minimized
    violated: list[str]
    exposure: Cents
    attempt: int
    outside_preset_search: bool  # some move isn't in any threat family's alphabet
    novel_moves: list[Move]
    labels: list[OracleLabel] = []  # the harness's answer key for this trace (red_bills)


class HuntResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str
    attempts: list[Attempt]
    best: Hit | None
    hits: int
    reason: str  # why the hunt stopped


# --- what the hunter sees -----------------------------------------------------------------------


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def snapshot(sb) -> dict[str, Any]:
    """The company as Red can observe it: its books, its controls, and its own capabilities.
    Never the oracle."""
    state: State = sb.run.state
    profile = sb.profile
    matrix = profile.approval_matrix
    vendors = []
    for v in state.vendors.values():
        accounts = [a for a in state.vendor_bank_accounts.values() if a.vendor == v.id]
        open_invoices = [
            {
                "id": i.id,
                "number": i.number,
                "amount": _money(i.amount),
                "status": i.status,
                "po": i.po,
                "due_day": i.due_date,
            }
            for i in state.invoices.values()
            if i.vendor == v.id and i.status in OPEN
        ]
        paid = sum(1 for i in state.invoices.values() if i.vendor == v.id and i.status == "paid")
        vendors.append(
            {
                "id": v.id,
                "name": v.name,
                "status": v.status,
                "po_required": v.po_required,
                "accounts": {a.id: a.status for a in accounts},
                "paid_invoices": paid,
                "open_invoices": open_invoices,
            }
        )
    vendors.sort(key=lambda x: (-len(x["open_invoices"]), x["id"]))
    tenants = [
        {
            "id": c.id,
            "name": c.name,
            "open_rent": _money(
                sum(
                    i.amount - i.paid
                    for i in state.customer_invoices.values()
                    if i.customer == c.id and i.status in ("open", "partially_paid")
                )
            ),
            "credit": _money(money_in.credit_balance(state, c.id)),
            "accounts_on_file": len(c.accounts_on_file),
        }
        for c in state.customers.values()
    ]
    return {
        "company": state.company,
        "today": state.day,
        "cash": {a.name: _money(a.balance) for a in state.bank_accounts.values()},
        "approval_threshold": _money(matrix.threshold),
        "approvers": [a.model_dump(mode="json") for a in matrix.approvers],
        "vendors": vendors,
        "tenants": tenants,
        "active_controls": [c.model_dump(mode="json") for c in sb.gate.checks],
        "policy": sb.policy.version,
        "attacker_profile": profile.attacker_capabilities.model_dump(),
    }


# --- running a hypothesis -------------------------------------------------------------------


def _money_summary(state: State) -> list[str]:
    """What an attacker can observe of where money went: refunds, and payments that left for an
    account other than the vendor's verified one. Account status, never the oracle's labels."""
    out = [
        f"refund {r.id} {_money(r.amount)} to {r.destination_account} for {r.customer}: {r.status}"
        for r in state.refunds.values()
    ]
    for p in state.payments.values():
        pi = state.payment_instructions[p.instruction]
        acct = state.vendor_bank_accounts.get(pi.payee_account)
        if acct is not None and acct.status != "verified":
            out.append(
                f"payment {p.id} {_money(pi.amount)} for {pi.invoice} to {acct.id} "
                f"({acct.status}): {p.status}"
            )
    return out[:12]


def _guard_summary(state: State) -> list[str]:
    out = []
    for e in state.events:
        if e.kind != "gate.verdict":
            continue
        verdict = e.payload.get("verdict", {})
        decision = verdict.get("decision", "allow")
        if decision == "allow":
            continue
        args = ", ".join(f"{k}={v}" for k, v in sorted(e.payload.get("args", {}).items()))
        fired = ", ".join(verdict.get("fired", [])) or "-"
        out.append(f"{decision} {e.payload.get('tool')}({args}) fired: {fired}")
    return out[:20]


def _executable(
    moves: Sequence[Move], seed: int, factory: SandboxFactory
) -> tuple[list[Move], list[str]]:
    """Drop moves the twin can't execute (bad params, beyond the attacker profile, not
    modeled), each with its reason. Each move is checked after the ones kept before it, since a
    refund request only makes sense once a deposit has landed."""
    kept: list[Move] = []
    dropped: list[str] = []
    for move in moves:
        try:
            replay(seed, [*kept, move], sandbox=factory)
        except IllegalMove as err:
            dropped.append(f"{move.kind}@{move.at}: {err}")
            continue
        except NotImplementedError as err:
            dropped.append(f"{move.kind}@{move.at}: not modeled ({err})")
            continue
        except (KeyError, ValueError, TypeError) as err:
            dropped.append(f"{move.kind}@{move.at}: bad parameters ({err})")
            continue
        kept.append(move)
    return kept, dropped


def red_bills(state: State, moves: Sequence[Move]) -> list[OracleLabel]:
    """Answer-key facts for invoices Red sent. Red is always the attacker, so a bill it sends is
    never owed: the harness books it as a duplicate of the same vendor's closest real bill (same
    PO first, then nearest amount). This comes from what the move did, not from the hypothesis."""
    sent = {
        (str(m.params.get("vendor")), str(m.params.get("number")))
        for m in moves
        if m.kind == "submit_invoice"
    }
    if not sent:
        return []
    red = [i for i in state.invoices.values() if (i.vendor, i.number) in sent]
    red_ids = {i.id for i in red}
    labels = []
    for bill in red:
        real = [
            i for i in state.invoices.values() if i.vendor == bill.vendor and i.id not in red_ids
        ]
        if not real:
            continue
        original = min(
            real,
            key=lambda i: (i.po != bill.po or bill.po is None, abs(i.amount - bill.amount), i.id),
        )
        labels.append(OracleLabel(subject=bill.id, label="duplicate_of", value=original.id))
    return labels


def replay_labeled(seed: int, moves: Sequence[Move], factory: SandboxFactory):
    """replay_detailed with the harness's own facts about Red's bills (red_bills)."""
    result, sb, oracle = replay_detailed(seed, list(moves), sandbox=factory)
    labels = red_bills(sb.run.state, moves)
    if labels:
        result, sb, oracle = replay_detailed(seed, list(moves), sandbox=factory, labels=labels)
    return result, sb, labels


def run_hypothesis(
    moves: Sequence[Move], seed: int, factory: SandboxFactory
) -> tuple[list[Move], Outcome]:
    kept, dropped = _executable(moves, seed, factory)
    if not kept:
        return kept, Outcome(violated=[], exposure=0, violations=[], guard=[], dropped=dropped)
    plan = dress(ThreatPlan(description="hunt", moves=kept, source="llm"), use_llm=False)
    result, sb, _ = replay_labeled(seed, plan.moves, factory)
    return plan.moves, Outcome(
        violated=sorted({v.invariant for v in result.violations}),
        exposure=result.exposure,
        violations=[f"{v.invariant}: {v.message}" for v in result.violations][:12],
        guard=_guard_summary(sb.run.state),
        money=_money_summary(sb.run.state),
        dropped=dropped,
    )


def _preset_alphabet(sb) -> set[str]:
    base = sb.run.state
    return {_move_key(m) for s in SCENARIOS.values() for m in build_alphabet(s, base, sb.profile)}


def _move_key(m: Move) -> str:
    params = {k: v for k, v in m.params.items() if k != "text"}
    return json.dumps([m.kind, m.at, params], sort_keys=True)


# --- the loop -------------------------------------------------------------------------------


def hunt(
    factory: SandboxFactory,
    *,
    seed: int = 7,
    attempts: int = 6,
    keep_going: bool = False,
    on_attempt: Callable[[Attempt], None] | None = None,
    pause: float | None = None,
    rng: random.Random | None = None,
) -> HuntResult:
    """Up to `attempts` rounds of: pause as if studying the company, take the next hypothesis
    from the PLAYBOOK, the twin runs it. Stops at the first hit unless `keep_going`, or when
    the playbook is used up. Deterministic: the same run gives the same hunt, so the demo
    lands on the same fix every time; pass `rng` to shuffle the playbook instead. `pause` is
    seconds per attempt (default from VANDAL_HUNT_PAUSE, else 3)."""
    if pause is None:
        pause = float(os.environ.get(PAUSE_ENV, DEFAULT_PAUSE))
    sb = factory(seed)
    preset = _preset_alphabet(sb)
    order = list(PLAYBOOK)
    if rng is not None:
        rng.shuffle(order)
    history: list[Attempt] = []
    best: Hit | None = None
    hits = 0
    rounds = min(attempts, len(order))
    reason = f"no invariant broken in {rounds} attempts"

    for n in range(1, rounds + 1):
        if pause > 0:
            time.sleep(pause)
        hyp = order[n - 1]
        ran, outcome = run_hypothesis(hyp.moves, seed, factory)
        attempt = Attempt(
            n=n,
            rationale=hyp.rationale,
            weak_spot=hyp.weak_spot,
            target_invariant=hyp.target_invariant,
            moves=ran or list(hyp.moves),
            outcome=outcome,
        )
        history.append(attempt)
        if on_attempt:
            on_attempt(attempt)
        if outcome.violated:
            hits += 1
            hit = _minimized_hit(ran, n, seed, factory, preset)
            if best is None or (-hit.exposure, len(hit.moves)) < (-best.exposure, len(best.moves)):
                best = hit
            if not keep_going:
                reason = f"attempt {n} broke {', '.join(outcome.violated)}"
                break
    else:
        if hits:
            reason = f"{hits} of {rounds} attempts broke an invariant"
    return HuntResult(
        policy=sb.policy.version, attempts=history, best=best, hits=hits, reason=reason
    )


def _minimized_hit(
    moves: list[Move], n: int, seed: int, factory: SandboxFactory, preset: set[str]
) -> Hit:
    def violated(ms: list[Move]) -> set[str]:
        return set(replay_labeled(seed, ms, factory)[0].violated)

    minimal = minimize_trace(moves, violated)
    final, _, labels = replay_labeled(seed, minimal, factory)
    novel = [m for m in minimal if _move_key(m) not in preset]
    return Hit(
        moves=minimal,
        violated=final.violated,
        exposure=final.exposure,
        attempt=n,
        outside_preset_search=bool(novel),
        novel_moves=novel,
        labels=labels,
    )


def window_for(moves: Sequence[Move]) -> str:
    """The threat family whose search window best covers a hunted attack, for CEGIS: the one
    with the most of its move kinds, ties to the first."""
    kinds = [m.kind for m in moves]
    return max(SCENARIOS, key=lambda name: sum(k in SCENARIOS[name].kinds for k in kinds))
