"""Scenario C (DESIGN 11): the Scenario A change request plus a cloned-voice inbound
"confirmation". It is the deepfake variant the demo replays after approving the patch (the
`deepfake_phone` class of the held-out variants), so it gets a trace of its own: under v0 the
money goes, under v1 the call is not a verification channel and the change is held, and a T1
that accepts inbound calls is beaten by it (which is why the spoofable lint rejects that T1)."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from vandal.sandbox import new_sandbox
from vandal.synth.lint import lint
from vandal.synth.templates import load_policy
from vandal.twin.profile import load_profile
from vandal.verify.replay import Trace, replay
from vandal.verify.variants import grid

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "c_deepfake.json"


@pytest.fixture(scope="module")
def trace() -> Trace:
    return Trace.load(TRACE)


def under(policy_name: str, trace: Trace):
    policy = load_policy(policy_name)
    return replay(
        trace.seed,
        trace.moves,
        sandbox=partial(new_sandbox, "bayline", policy=policy),
        days=trace.days,
    )


def test_under_v0_the_deepfake_confirms_the_change_and_the_money_goes(trace) -> None:
    r = under("v0", trace)
    assert {"INV-4", "INV-5"} <= set(r.violated)
    assert r.exposure == 4_000_000


def test_under_v1_the_inbound_call_is_not_a_verification_channel(trace) -> None:
    r = under("v1", trace)
    assert r.violated == [] and r.exposure == 0


def test_a_t1_that_accepts_inbound_calls_is_beaten_and_linted(trace) -> None:
    # Before approval, so T2's binding can't save it: the approval binds the attacker's account
    # and only the verification channel stands between the deepfake and the money (R6).
    moves = [m.model_copy(update={"at": 0}) for m in trace.moves]
    early = trace.model_copy(update={"moves": moves})
    r = under("t1_phone_in", early)
    assert "INV-4" in r.violated and r.exposure == 4_000_000
    assert under("v1", early).violated == []
    profile = load_profile("bayline")
    policy = load_policy("t1_phone_in")
    t1 = next(c for c in policy.controls if c.template == "T1")
    assert any(f.lint == "spoofable" for f in lint(t1, profile.attacker_capabilities))


def test_the_variant_grid_holds_out_both_deepfake_classes() -> None:
    sb = new_sandbox()
    classes = {v.threat_class for v in grid(sb.run.state, sb.profile)}
    assert {"deepfake_phone", "deepfake_video"} <= classes
    v007 = [
        v
        for v in grid(sb.run.state, sb.profile)
        if v.threat_class == "deepfake_phone" and v.name.startswith("V-007/after_approval")
    ]
    assert v007, "the demo's vendor and timing are in the held-out grid"
