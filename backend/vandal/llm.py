"""L0: Claude wrapper with structured output, a cache, and playback.

The cache is keyed by (prompt_version, agent, step, sha256(input)).

L0 hasn't landed yet. This file fixes the one call the rest of the code uses, `structured()`, so
callers (synth/propose.py today; the LLM Operator, Red, and explanations later) can be written
against it now. Until L0 implements it, it raises LLMUnavailable and every caller falls back to
its deterministic path.
"""

from __future__ import annotations

from pydantic import BaseModel


class LLMUnavailable(RuntimeError):
    """No model to call: L0 not built yet, no API key, playback cache miss, or timeout."""


def structured[T: BaseModel](
    *,
    agent: str,
    step: str,
    prompt_version: str,
    system: str,
    prompt: str,
    schema: type[T],
    model_env: str = "MODEL_SYNTH",
) -> T:
    """One structured Claude call, returning an instance of `schema`.

    agent/step/prompt_version and the prompt make the cache key. `model_env` names the env var
    holding the model id (MODEL_AGENT or MODEL_SYNTH).
    """
    raise LLMUnavailable("vandal/llm.py (L0) hasn't landed yet")
