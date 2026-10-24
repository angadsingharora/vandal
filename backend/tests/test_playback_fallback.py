"""L0 done-when, per caller: with DEMO_PLAYBACK=true, no API key, and an empty cache, every
LLM-touching path takes its deterministic fallback instead of failing. The wrapper raises
LLMUnavailable on the miss (tests/test_llm.py); these tests check that each caller catches it."""

from __future__ import annotations

from functools import partial

import pytest

from tests.test_blue import TRACE
from vandal.guard.explain import explain
from vandal.operator.intake import extract, extract_deterministic
from vandal.sandbox import new_sandbox
from vandal.search import red
from vandal.synth.propose import LLMProposer, ProposalContext
from vandal.twin.profile import load_profile
from vandal.verify.messy import messy_items
from vandal.verify.replay import Trace, replay_detailed


@pytest.fixture(autouse=True)
def _playback(monkeypatch) -> None:
    # conftest already cleared the key and gave this test an empty LLM_CACHE_DIR.
    monkeypatch.setenv("DEMO_PLAYBACK", "true")


def test_intake_falls_back_to_the_deterministic_reader() -> None:
    sb = new_sandbox()
    item = messy_items(sb.run.state, sb.profile)[0]
    got = extract(item.message, sb.run.state, sb.profile)
    assert got == extract_deterministic(item.message, sb.run.state, sb.profile)
    assert got.source == "deterministic"


def test_red_falls_back_to_keywords_and_templates() -> None:
    p = red.plan("a vendor emails new bank details after approval", partial(new_sandbox, "bayline"))
    assert p.scenario == "a" and p.moves
    assert any("playback" in n and "keywords" in n for n in p.notes)
    assert all("text" in m.params for m in p.moves if red.template_for(m))


def test_propose_falls_back_to_the_sweep() -> None:
    ctx = ProposalContext(
        iteration=1, gap="approval_binding", diagnosis={}, base=[], feedback=[], tried=[]
    )
    proposer = LLMProposer(load_profile("bayline"))
    proposals = proposer.propose(ctx)
    assert proposals and all(p.source == "sweep" for p in proposals)
    assert "playback" in proposer.notes[0]


def test_explain_falls_back_to_the_deterministic_explanation() -> None:
    _, sb, _ = replay_detailed(7, Trace.load(TRACE).moves, sandbox=partial(new_sandbox, "bayline"))
    e = explain(sb.run.state, "payment", "PAY-0057")
    assert e.source == "deterministic" and e.claims
    assert any("playback" in n for n in e.notes)
