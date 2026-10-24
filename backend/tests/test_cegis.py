"""R8 done-when: starting from R5's diagnosis, CEGIS ends at a control set with no violations
within k and 0 legitimate blocks, with at least one refuted candidate in the log; it works with
--no-llm; and exhausting the iterations gives an honest "cannot auto-repair". Searches run at
depth 2 here to stay fast; the CLI defaults to depth 3."""

from __future__ import annotations

import json
from functools import partial

import pytest

from vandal import llm
from vandal.cli import main
from vandal.contracts.controls import Control
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.synth.cegis import cegis
from vandal.synth.coverage import diagnose
from vandal.synth.objective import Measurement, rank, score
from vandal.synth.propose import GAP_TEMPLATES, LLMProposer, ProposalContext, SweepProposer
from vandal.synth.templates import V0, Policy
from vandal.twin.profile import load_profile
from vandal.verify.replay import replay_detailed

PROFILE = load_profile()
T2 = Control(template="T2", params={"bound_fields": ["payee_account"]})


def factory_for(policy):
    return partial(new_sandbox, "bayline", policy=policy)


@pytest.fixture(scope="module")
def repaired():
    return cegis(
        V0, factory_for, profile=PROFILE, proposer=SweepProposer(PROFILE), depth=2, workers=4
    )


@pytest.mark.slow
def test_cegis_repairs_scenario_a(repaired) -> None:
    assert repaired.status == "repaired"
    templates = [c.template for c in repaired.policy.controls]
    assert templates == ["T2", "T1"]  # binding first, then verification (DESIGN 11)
    t1 = repaired.policy.controls[1].params
    assert t1["contact_as_of"] == "before_request" and "phone_in" not in t1["accepted_channels"]
    survivor = next(e for e in repaired.log if e.outcome == "survived")
    assert survivor.measurement.counterexamples == 0
    assert survivor.measurement.legit_blocked == 0 and survivor.measurement.legit_failed == 0


@pytest.mark.slow
def test_the_log_shows_refuted_candidates(repaired) -> None:
    outcomes = [e.outcome for e in repaired.log]
    assert outcomes.count("counterexample") >= 2 and "false_positive" in outcomes
    t2 = next(e for e in repaired.log if e.candidate.startswith("T2"))
    assert t2.counterexample and t2.counterexample[0].at == 0  # the change *before* approval
    current = next(
        e
        for e in repaired.log
        if "contact_as_of=current" in e.candidate and e.outcome == "counterexample"
    )
    assert [m.params["fields"] for m in current.counterexample] == ["contact", "bank"]
    assert all(e.base == [] for e in repaired.log if e.iteration == 1)
    assert all(e.base for e in repaired.log if e.iteration == 2)  # T2 kept as the base


@pytest.mark.slow
def test_exhausted_iterations_say_cannot_auto_repair() -> None:
    r = cegis(
        V0, factory_for, profile=PROFILE, proposer=SweepProposer(PROFILE), depth=2, max_iterations=1
    )
    assert r.status == "cannot_auto_repair" and r.policy is None
    assert "best partial fix" in r.reason and r.chosen[0].startswith("T2")


def test_nothing_to_repair_when_search_finds_nothing() -> None:
    v1 = Policy.load("policies/v1.json")
    r = cegis(v1, factory_for, profile=PROFILE, proposer=SweepProposer(PROFILE), depth=1)
    assert r.status == "nothing_to_repair"


@pytest.mark.slow
def test_llm_candidates_are_validated_linted_and_searched(monkeypatch) -> None:
    """With a model answering, its candidates go through the same checks: an invalid one is
    dropped, a spoofable one is refuted by lint, and only search decides the rest."""

    def fake(*, schema, prompt, **_):
        assert json.loads(prompt)["gap"] == "verification_channel"
        return schema.model_validate(
            {
                "candidates": [
                    {
                        "template": "T1",
                        "params": [{"key": "accepted_channels", "value": ["carrier_pigeon"]}],
                        "rationale": "invalid",
                    },
                    {
                        "template": "T1",
                        "params": [
                            {"key": "accepted_channels", "value": ["phone_outbound", "phone_in"]}
                        ],
                        "rationale": "accept the vendor calling in too",
                    },
                    {
                        "template": "T1",
                        "params": [
                            {"key": "accepted_channels", "value": ["phone_outbound"]},
                            {"key": "contact_as_of", "value": "before_request"},
                        ],
                        "rationale": "call back the number on file before the request",
                    },
                ]
            }
        )

    monkeypatch.setattr(llm, "structured", fake)
    proposer = LLMProposer(PROFILE)
    t2_only = Policy(version="t2", controls=[T2])
    r = cegis(t2_only, factory_for, profile=PROFILE, proposer=proposer, depth=2, workers=4)
    assert r.status == "repaired" and r.iterations == 1
    assert [e.outcome for e in r.log] == ["lint", "survived"]
    assert all(e.source == "llm" for e in r.log)
    assert any("dropped invalid T1" in n for n in r.notes)


def test_llm_unavailable_falls_back_to_the_sweep() -> None:
    ctx = ProposalContext(
        iteration=1, gap="approval_binding", diagnosis={}, base=[], feedback=[], tried=[]
    )
    proposer = LLMProposer(PROFILE)
    proposals = proposer.propose(ctx)
    assert proposals and all(p.source == "sweep" for p in proposals)
    assert "LLM unavailable" in proposer.notes[0]


def test_sweep_covers_every_gap_and_skips_tried() -> None:
    sweep = SweepProposer(PROFILE)
    for gap in GAP_TEMPLATES:
        ctx = ProposalContext(iteration=1, gap=gap, diagnosis={}, base=[], feedback=[], tried=[])
        assert sweep.propose(ctx), gap
    first = sweep.propose(
        ProposalContext(
            iteration=1, gap="approval_binding", diagnosis={}, base=[], feedback=[], tried=[]
        )
    )[0]
    again = sweep.propose(
        ProposalContext(
            iteration=1,
            gap="approval_binding",
            diagnosis={},
            base=[],
            feedback=[],
            tried=[first.label],
        )
    )
    assert first.label not in {p.label for p in again}


def test_objective() -> None:
    risk = PROFILE.risk_appetite
    clean = Measurement(
        residual_exposure=0,
        counterexamples=0,
        legit_blocked=0,
        legit_failed=0,
        holds=9,
        templates=2,
        params=4,
    )
    blocky = clean.model_copy(update={"legit_blocked": 1, "holds": 0})
    assert score(clean, risk) == 9 * 5_000 and score(blocky, risk) == 500_000
    beaten = clean.model_copy(update={"counterexamples": 1, "residual_exposure": 10})
    assert sorted([beaten, blocky, clean], key=lambda m: rank(m, risk)) == [clean, blocky, beaten]


def test_coverage_sees_a_callback_to_a_swapped_contact() -> None:
    weak = Policy(
        version="w",
        controls=[
            Control(
                template="T1",
                params={"accepted_channels": ["phone_outbound"], "contact_as_of": "current"},
            ),
            T2,
        ],
    )
    moves = [
        Move(
            kind="change_request",
            at=0,
            params={"vendor": "V-007", "fields": f, "channel": "email", "sender": "lookalike"},
        )
        for f in ("contact", "bank")
    ]
    result, sb, _ = replay_detailed(7, moves, sandbox=factory_for(weak), days=2)
    d = diagnose(sb.run.state, result.violations)
    assert d.gap == "verification_channel" and "contact changed on day 0" in d.reason


@pytest.mark.slow
def test_vandal_synth_cli(tmp_path, capsys) -> None:
    args = [
        "synth",
        "--no-llm",
        "--depth",
        "1",
        "--workers",
        "1",
        "--out",
        str(tmp_path),
        "--max-iterations",
        "1",
    ]
    assert main(args) == 1  # depth 1 can't see past T2 in one iteration
    assert "cannot_auto_repair" in capsys.readouterr().out
