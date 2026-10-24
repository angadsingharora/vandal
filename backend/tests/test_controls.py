"""R6: control templates, the policy store, lints, evidence-gated holds, and the two done-whens:
T1 + T2 installed by hand leave no violations, and a T1 accepting phone_in is rejected by the
spoofable lint (and beaten by search without it)."""

from __future__ import annotations

import os
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

from vandal.cli import main
from vandal.contracts.controls import Control
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.lint import lint
from vandal.synth.templates import Policy, PolicyStore, describe
from vandal.twin.profile import load_profile
from vandal.verify.invariants import check
from vandal.verify.replay import Trace, replay_detailed

ROOT = Path(__file__).resolve().parents[1]
V1 = Policy.load(ROOT / "policies" / "v1.json")
PHONE_IN = Policy.load(ROOT / "policies" / "t1_phone_in.json")
A = SCENARIOS["a"]
CAPS = load_profile().attacker_capabilities


def T1(**p) -> Control:
    return Control(template="T1", params={"accepted_channels": ["phone_outbound", "portal"], **p})


def T2(**p) -> Control:
    return Control(template="T2", params={"bound_fields": ["amount", "payee_account"], **p})


def cr(at: int, fields: str = "bank") -> Move:
    return Move(
        kind="change_request",
        at=at,
        params={"vendor": "V-007", "fields": fields, "channel": "email", "sender": "lookalike"},
    )


def confirm(at: int, channel: str = "phone_in") -> Move:
    return Move(
        kind="inbound_confirmation",
        at=at,
        params={"vendor": "V-007", "channel": channel, "voice_match": 95},
    )


def run(policy: Policy | None, moves: list[Move]):
    return replay_detailed(7, moves, sandbox=partial(new_sandbox, "bayline", policy=policy), days=2)


# --- templates and the policy store ---------------------------------------------------------


@pytest.mark.parametrize(
    ("control", "stages"),
    [
        (T1(), {"change_request", "pre_execute"}),
        (T2(), {"pre_execute"}),
        (Control(template="T3", params={}), {"submit"}),
        (
            Control(template="T4", params={"amount_tol_pct": 1, "window_days": 30}),
            {"invoice.match"},
        ),
        (
            Control(template="T5", params={"window_days": 5, "threshold": 2_500_000}),
            {"pre_approve"},
        ),
        (Control(template="T6", params={}), {"refund"}),
    ],
)
def test_every_template_compiles(control, stages) -> None:
    checks = control.compile()
    assert checks and {c.stage for c in checks} == stages
    assert len({c.id for c in checks}) == len(checks)
    assert describe(control).startswith(control.template)


@pytest.mark.parametrize(
    "bad",
    [
        Control(template="T1", params={"accepted_channels": []}),
        Control(template="T1", params={"accepted_channels": ["carrier_pigeon"]}),
        Control(template="T2", params={"bound_fields": ["color"]}),
        Control(template="T4", params={"window_days": 7}),
        Control(template="T5", params={"threshold": 0}),
    ],
)
def test_invalid_params_are_rejected(bad) -> None:
    with pytest.raises(ValidationError):
        bad.compile()


def test_check_ids_depend_on_params() -> None:
    a, b = T1().compile()[0].id, T1(contact_as_of="current").compile()[0].id
    assert a != b and a == T1().compile()[0].id


def test_policy_store_records_parent_and_diff() -> None:
    store = PolicyStore()
    v1 = store.derive("v0", "v1", add=[T2()])
    v2 = store.derive("v1", "v2", add=[T1()], remove=[T2()])
    assert (v1.parent, v2.parent) == ("v0", "v1")
    assert v2.controls == [T1()]
    assert v2.diff == [f"- {describe(T2())}", f"+ {describe(T1())}"]
    assert V1.diff and all(line.startswith("+ ") for line in V1.diff)


# --- lints ----------------------------------------------------------------------------------


def test_spoofable_lint_follows_attacker_capabilities() -> None:
    (f,) = lint(T1(accepted_channels=["phone_outbound", "phone_in"]), CAPS)
    assert f.lint == "spoofable" and "phone_in" in f.message
    assert [x.lint for x in lint(T1(accepted_channels=["video"]), CAPS)] == ["spoofable"]
    honest = CAPS.model_copy(update={"spoof_caller_id": False, "clone_voice": False})
    assert lint(T1(accepted_channels=["phone_in"]), honest) == []
    assert lint(T1(), CAPS) == []


def test_block_where_hold_works() -> None:
    assert [f.lint for f in lint(T2(on_mismatch="block"), CAPS)] == ["block_where_hold_works"]
    assert lint(T2(), CAPS) == []
    assert lint(Control(template="T3", params={}), CAPS) == []  # a second execution must block


def test_overfit_on_the_counterexample_amount() -> None:
    tuned = Control(template="T5", params={"window_days": 5, "threshold": 3_999_000})
    assert [f.lint for f in lint(tuned, CAPS, [4_000_000])] == ["overfit"]
    general = Control(template="T5", params={"window_days": 5, "threshold": 2_500_000})
    assert lint(general, CAPS, [4_000_000]) == []


# --- evidence-gated holds -------------------------------------------------------------------


def test_v1_holds_scenario_a_and_the_callback_reaches_the_real_vendor() -> None:
    trace = Trace.load(ROOT / "scenarios" / "a_manual.json")
    result, sb, _ = run(V1, trace.moves)
    state = sb.run.state
    assert result.violations == [] and result.exposure == 0
    (change,) = state.change_requests.values()
    assert change.status == "held"
    (call,) = state.evidence.values()
    assert (call.channel, call.direction, call.confirms) == ("phone_outbound", "outbound", False)
    assert call.contact == next(
        c.id for c in state.vendor_contacts.values() if c.vendor == "V-007" and c.valid_to is None
    )
    verdict = next(
        e
        for e in state.events
        if e.kind == "gate.verdict" and e.payload["tool"] == "vendors.change_request"
    )
    (req,) = verdict.payload["verdict"]["facts"]["gate.requires"]
    assert req["contact_as_of"] == "before_request"
    # INV-1042 still went out, to the account that was approved and verified.
    pay = next(
        p
        for p in state.payments.values()
        if state.payment_instructions[p.instruction].invoice == "INV-1042"
    )
    assert state.payment_instructions[pay.instruction].payee_account == "BA-0007"


def test_inbound_evidence_never_clears_an_outbound_only_hold() -> None:
    result, sb, _ = run(V1, [cr(0), confirm(0), confirm(0, "video")])
    state = sb.run.state
    assert result.violations == []
    assert {e.channel for e in state.evidence.values()} == {"phone_outbound", "phone_in", "video"}
    assert next(iter(state.change_requests.values())).status == "held"


def test_genuine_change_is_applied_once_the_callback_confirms() -> None:
    """In a world with no attacker, the real vendor confirms and the change goes through,
    verified by the outbound callback."""
    from vandal.contracts.entities import Actor
    from vandal.twin.flows import ChangeRequestArgs
    from vandal.twin.world import settle

    sb = new_sandbox(policy=V1)
    op = sb.operator
    ev_args = ChangeRequestArgs(
        vendor="V-004",
        channel="email",
        sender="ar@greenlinels.com",
        routing="121000358",
        account="5550001111",
    )
    result = sb.tools.call(Actor(id="OP-1", role="operator"), "vendors.change_request", ev_args)
    assert result.verdict.decision == "hold"
    change = next(iter(sb.run.state.change_requests))
    op._verify(change, result.verdict.facts["gate.requires"], sb.tools)
    settle(sb.run, sb.tools, op, None)  # the legitimate world answers: confirmed
    state = sb.run.state
    assert state.change_requests[change].status == "applied"
    new = next(a for a in state.vendor_bank_accounts.values() if a.source.endswith(change))
    assert (new.status, new.verified_by) == ("verified", "phone_outbound")
    cleared = [
        e
        for e in state.events
        if e.kind == "gate.verdict" and e.payload["tool"] == "vendors.apply_change"
    ][-1]
    assert cleared.payload["verdict"]["decision"] == "allow"
    assert cleared.payload["verdict"]["facts"]["gate.cleared_evidence"]


def test_contact_as_of_current_is_beaten_by_a_contact_swap() -> None:
    weak = Policy(version="t1-current", controls=[T1(contact_as_of="current"), T2()])
    result, _, _ = run(weak, [cr(0, "contact"), cr(0)])
    assert result.violated == ["INV-4"] and result.exposure == 4_000_000
    strong, _, _ = run(V1, [cr(0, "contact"), cr(0)])
    assert strong.violations == []


def test_t2_alone_is_beaten_by_a_change_before_approval() -> None:
    t2 = Policy(version="t2", controls=[T2()])
    assert run(t2, Trace.load(ROOT / "scenarios" / "a_manual.json").moves)[0].violations == []
    assert run(t2, [cr(0)])[0].violated == ["INV-4", "INV-5"]


def test_v1_costs_nothing_on_legitimate_operations() -> None:
    sb = new_sandbox(policy=V1).operate(5)
    state = sb.run.state
    assert check(state) == []
    assert all(i.status == "paid" for i in state.invoices.values())
    holds = [
        e
        for e in state.events
        if e.kind == "gate.verdict"
        and e.payload["verdict"]["decision"] != "allow"
        and e.payload["tool"] != "approvals.request"
    ]
    assert holds == []


# --- done when ------------------------------------------------------------------------------


@pytest.mark.slow
def test_v1_search_finds_no_violations() -> None:
    """Depth 2 by default; VANDAL_DEPTH4=1 runs the full depth-4 check (~3.5 min)."""
    depth = 4 if os.environ.get("VANDAL_DEPTH4") else 2
    result = search(
        partial(new_sandbox, "bayline", policy=V1), A, depth=depth, workers=8 if depth == 4 else 1
    )
    assert result.findings == [] and result.best is None
    assert len(result.levels) == depth


def test_phone_in_t1_is_rejected_by_the_spoofable_lint(capsys) -> None:
    assert main(["search", "--policy", str(ROOT / "policies" / "t1_phone_in.json")]) == 2
    out = capsys.readouterr().out
    assert "lint spoofable" in out and "rejected by lint" in out


@pytest.mark.slow
def test_without_the_lint_search_beats_it_with_inbound_confirmation() -> None:
    result = search(partial(new_sandbox, "bayline", policy=PHONE_IN), A, depth=4)
    best = result.best
    assert best is not None and len(best.moves) == 2
    assert [m.kind for m in best.moves] == ["change_request", "inbound_confirmation"]
    assert "INV-4" in best.violated and best.exposure == 4_000_000
