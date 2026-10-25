"""The committed LLM recordings (backend/llm_cache/) are what DEMO_PLAYBACK serves at the venue.
Every entry must be well formed, must validate against the schema of the caller that recorded
it, and must be keyed by its content alone: recomputing the key from the stored request gives
the file name, so the same demo click replays from cache regardless of run id or time."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import BaseModel

from vandal import llm
from vandal.guard import explain
from vandal.operator import intake
from vandal.search import hunt, red
from vandal.synth import propose

CACHE = llm.BACKEND / "llm_cache"
ENTRIES = sorted(CACHE.glob("*.json"))

# (agent, step pattern) -> the schema that caller asks for
SCHEMAS: list[tuple[str, str, type[BaseModel]]] = [
    ("operator", r"intake", intake._LLMExtraction),
    ("red", r"plan", red._LLMPlan),
    ("red", r"content", red._LLMTexts),
    ("red", r"hunt-\d+", hunt._Hypothesis),
    ("synth", r"propose-\d+", propose._LLMProposal),
    ("blue", r"explain", explain._LLMExplanation),
]
SECRET = re.compile(r"sk-ant-|postgresql\+psycopg://[^ ]*:[^ ]*@")


def schema_for(agent: str, step: str) -> type[BaseModel]:
    for a, pattern, schema in SCHEMAS:
        if a == agent and re.fullmatch(pattern, step):
            return schema
    raise AssertionError(f"no caller records {agent}/{step}")


def test_the_cache_is_recorded() -> None:
    assert ENTRIES, "backend/llm_cache is empty: playback has nothing to serve"
    agents = {p.name.split(".")[1] for p in ENTRIES}
    assert agents >= {"operator", "red", "synth", "blue"}, agents


@pytest.mark.parametrize("path", ENTRIES, ids=[p.stem[:48] for p in ENTRIES])
def test_entry_is_valid_and_keyed_by_content(path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not SECRET.search(text), f"{path.name} looks like it holds a secret"
    entry = json.loads(text)
    assert set(entry) == {"cache_key", "request", "response"}
    assert entry["cache_key"] == path.stem
    prompt_version, agent, step, digest = path.stem.split(".")
    schema = schema_for(agent, step)
    schema.model_validate(entry["response"])
    req = entry["request"]
    assert {"model", "system", "prompt"} <= set(req) <= {"model", "served_by", "system", "prompt"}
    assert (
        llm.cache_key(
            agent=agent,
            step=step,
            prompt_version=prompt_version,
            model=req["model"],
            system=req["system"],
            prompt=req["prompt"],
            schema=schema,
        )
        == path.stem
    )
    assert not re.search(r"run_[0-9a-f]{6,}|\d{4}-\d{2}-\d{2}T\d{2}:", req["prompt"]), (
        "a run id or wall-clock timestamp in the prompt would make the key unstable"
    )
