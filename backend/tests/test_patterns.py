"""B6: fraud-pattern recall. Cited messages are matched against known patterns, the match rides
along with "why?" and never changes a decision, recordings replay offline, and every Moss failure
falls back to the lexical scorer. Moss is faked except in the live check, which runs only with
VANDAL_LIVE_MOSS=1 (it indexes the library in the project named in backend/.env)."""

from __future__ import annotations

import os
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app
from vandal.guard import patterns
from vandal.guard.explain import explain
from vandal.guard.patterns import Hit, MossUnavailable, recall
from vandal.sandbox import new_sandbox
from vandal.verify.replay import Trace, replay_detailed

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"
BANK_CHANGE = (
    "Updated remittance details - Acme Plumbing\nPlease note Acme Plumbing has moved banking "
    "providers. Effective immediately, please remit all open invoices to:\nRouting: 026012345\n"
    "Account: 1234567890\nThe previous account ending 4421 will be closed this week."
)
STATUS = "Re: Acme remittance\nChecking on the status of our open invoices."


@pytest.fixture
def scenario_a():
    _, sb, _ = replay_detailed(7, Trace.load(TRACE).moves, sandbox=partial(new_sandbox, "bayline"))
    return sb.run.state


def test_lexical_fallback_names_the_pattern() -> None:
    bank = recall(BANK_CHANGE)
    assert bank.source == "lexical" and "MOSS_PROJECT_ID" in (bank.note or "")
    assert bank.match is not None and bank.match.id == "FP-bank-moved"
    status = recall(STATUS)
    assert status.match is None and status.hits[0].id == "RP-status"


def test_library_ids_are_unique_and_index_name_tracks_content() -> None:
    ids = [p.id for p in patterns.LIBRARY]
    assert len(ids) == len(set(ids))
    assert {p.kind for p in patterns.LIBRARY} == {"fraud", "routine"}
    assert patterns.LIBRARY_VERSION in patterns.INDEX_NAME


def test_moss_answer_is_recorded_and_replayed(monkeypatch) -> None:
    calls = []

    def fake(text):
        calls.append(text)
        return [Hit(id="FP-bank-moved", kind="fraud", title="Bank details changed", score=1.0)]

    monkeypatch.setattr(patterns._moss, "query", fake)
    first = recall(BANK_CHANGE)
    assert first.source == "moss" and first.match and first.match.id == "FP-bank-moved"
    second = recall(BANK_CHANGE)
    assert second.source == "recorded" and second.hits == first.hits and len(calls) == 1
    monkeypatch.setenv("DEMO_PLAYBACK", "true")
    assert recall(BANK_CHANGE).source == "recorded"


def test_playback_miss_never_calls_moss(monkeypatch) -> None:
    def boom(_text):
        raise AssertionError("playback must not call Moss")

    monkeypatch.setattr(patterns._moss, "query", boom)
    monkeypatch.setenv("DEMO_PLAYBACK", "true")
    out = recall(BANK_CHANGE)
    assert out.source == "lexical" and "playback" in (out.note or "")


def test_moss_failure_falls_back(monkeypatch) -> None:
    def down(_text):
        raise MossUnavailable("TimeoutError: ")

    monkeypatch.setattr(patterns._moss, "query", down)
    out = recall(BANK_CHANGE)
    assert out.source == "lexical" and out.match and "TimeoutError" in (out.note or "")
    assert not list(patterns.cache_dir().glob("*.json"))  # a fallback is never recorded


def test_why_carries_the_match_outside_the_claims(scenario_a) -> None:
    answer = explain(scenario_a, "change_request", "CR-0001", use_llm=False)
    assert [r.message for r in answer.resembles] == [scenario_a.change_requests["CR-0001"].message]
    assert answer.resembles[0].match and answer.resembles[0].match.id == "FP-bank-moved"
    # advisory: no claim cites a pattern, and the claims are the same with recall off
    assert not any(x.startswith(("FP-", "RP-")) for c in answer.claims for x in c.cites)
    bare = explain(scenario_a, "change_request", "CR-0001", use_llm=False, patterns=False)
    assert bare.claims == answer.claims and bare.resembles == []


def test_payment_why_reaches_the_message_through_the_chain(scenario_a) -> None:
    answer = explain(scenario_a, "payment", "PAY-0057", use_llm=False)
    assert any(r.match and r.match.id == "FP-bank-moved" for r in answer.resembles)


def test_pattern_routes() -> None:
    with TestClient(create_app(persist=False)) as client:
        lib = client.get("/patterns").json()
        assert lib["moss"] is False and len(lib["patterns"]) == len(patterns.LIBRARY)
        out = client.post("/patterns/recall", json={"text": BANK_CHANGE}).json()
        assert out["match"]["id"] == "FP-bank-moved" and out["source"] == "lexical"
        assert client.post("/patterns/recall", json={"text": "  "}).status_code == 400


@pytest.mark.skipif(not os.environ.get("VANDAL_LIVE_MOSS"), reason="live: set VANDAL_LIVE_MOSS=1")
def test_live_moss(monkeypatch) -> None:
    from dotenv import dotenv_values

    for name, value in dotenv_values(patterns.BACKEND / ".env").items():
        if value and name.startswith("MOSS_") and name not in os.environ:
            monkeypatch.setenv(name, value)
    out = recall(BANK_CHANGE)
    assert out.source == "moss", out.note
    assert out.match and out.match.id == "FP-bank-moved"
    assert recall(STATUS).match is None
