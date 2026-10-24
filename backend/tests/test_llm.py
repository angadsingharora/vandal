"""L0: the Claude wrapper. A structured call works, a repeated call hits the cache, playback works
with no API key, and every failure surfaces as LLMUnavailable so callers fall back. The API is
faked except in the live check, which runs only with VANDAL_LIVE_LLM=1 (and spends a few cents)."""

from __future__ import annotations

import os
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from vandal import llm


class Answer(BaseModel):
    vendor: str
    amount: float


CALL = dict(
    agent="operator",
    step="intake",
    prompt_version="t1",
    system="Extract the vendor and amount.",
    prompt="Invoice from Acme Plumbing for $1,250.00",
    schema=Answer,
    model_env="MODEL_AGENT",
)


class FakeMessages:
    def __init__(self, reply=None, stop_reason="end_turn", error=None) -> None:
        self.reply, self.stop_reason, self.error = reply, stop_reason, error
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            parsed_output=self.reply,
            stop_reason=self.stop_reason,
            stop_details=SimpleNamespace(category="cyber")
            if self.stop_reason == "refusal"
            else None,
            model=kwargs["model"],
        )


def fake_api(monkeypatch, **kwargs) -> FakeMessages:
    messages = FakeMessages(**kwargs)
    monkeypatch.setattr(
        llm, "_client_cache", SimpleNamespace(beta=SimpleNamespace(messages=messages))
    )
    return messages


def test_structured_call_then_cache_hit(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_AGENT", "claude-sonnet-5-5")
    api = fake_api(monkeypatch, reply=Answer(vendor="Acme Plumbing", amount=1250.0))
    assert llm.structured(**CALL) == Answer(vendor="Acme Plumbing", amount=1250.0)
    assert llm.structured(**CALL) == Answer(vendor="Acme Plumbing", amount=1250.0)
    assert len(api.calls) == 1  # the repeat came from the cache
    sent = api.calls[0]
    assert sent["model"] == "claude-sonnet-5-5" and sent["output_format"] is Answer
    assert sent["fallbacks"] == "default"


def test_cache_key_changes_with_the_input(monkeypatch) -> None:
    api = fake_api(monkeypatch, reply=Answer(vendor="Acme", amount=1.0))
    llm.structured(**CALL)
    llm.structured(**{**CALL, "prompt": "Invoice from Bolt Electric for $90"})
    llm.structured(**{**CALL, "prompt_version": "t2"})
    assert len(api.calls) == 3


def test_playback_serves_recordings_without_a_key(monkeypatch) -> None:
    fake_api(monkeypatch, reply=Answer(vendor="Acme", amount=1.0))
    llm.structured(**CALL)  # record
    monkeypatch.setattr(llm, "_client_cache", None)  # no key, no client
    monkeypatch.setenv("DEMO_PLAYBACK", "true")
    assert llm.structured(**CALL).vendor == "Acme"
    with pytest.raises(llm.LLMUnavailable, match="playback"):
        llm.structured(**{**CALL, "prompt": "never recorded"})


def test_no_key_is_unavailable() -> None:
    with pytest.raises(llm.LLMUnavailable, match="ANTHROPIC_API_KEY"):
        llm.structured(**CALL)


def test_refusal_is_unavailable_and_not_cached(monkeypatch) -> None:
    api = fake_api(monkeypatch, reply=None, stop_reason="refusal")
    for _ in range(2):
        with pytest.raises(llm.LLMUnavailable, match="refused"):
            llm.structured(**CALL)
    assert len(api.calls) == 2


def test_timeout_is_unavailable(monkeypatch) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_api(monkeypatch, error=anthropic.APITimeoutError(request=request))
    with pytest.raises(llm.LLMUnavailable, match="timed out"):
        llm.structured(**CALL)


@pytest.mark.skipif(not os.environ.get("VANDAL_LIVE_LLM"), reason="live: set VANDAL_LIVE_LLM=1")
def test_live_call(monkeypatch) -> None:
    from dotenv import dotenv_values

    # Through monkeypatch, so the key is gone again for the tests after this one.
    for name, value in dotenv_values(llm.BACKEND / ".env").items():
        if value and name not in os.environ:
            monkeypatch.setenv(name, value)
    reply = llm.structured(**CALL)
    assert "acme" in reply.vendor.lower() and reply.amount == pytest.approx(1250.0)
