"""L0: Claude wrapper with structured output, a cache, and playback.

The cache is keyed by (prompt_version, agent, step, sha256(input)), where the input is the model,
the system prompt, the prompt, and the output schema. Each entry is one JSON file under
LLM_CACHE_DIR (default backend/llm_cache/), so recordings can be committed and replayed offline.

  - A cache hit is served without calling the API, live or not.
  - DEMO_PLAYBACK=true serves only from the cache: a miss raises LLMUnavailable, no key needed.
  - No API key, a timeout (LLM_TIMEOUT seconds), an API error, a refusal, or an unparseable reply
    raise LLMUnavailable, and every caller falls back to its deterministic path.

Secrets come from backend/.env (see .env.example); set VANDAL_DOTENV=0 to skip loading it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parents[1]
# Same as .env.example, so a recording made with the defaults replays without a .env.
DEFAULT_MODELS = {"MODEL_AGENT": "claude-sonnet-5-5", "MODEL_SYNTH": "claude-opus-5-5"}
MAX_TOKENS = 16000
EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client_cache: Any = None


class LLMUnavailable(RuntimeError):
    """No model to call: no API key, playback cache miss, timeout, API error, or refusal."""


def load_env() -> None:
    """Load backend/.env into os.environ without overriding what is already set."""
    if os.environ.get("VANDAL_DOTENV", "1") == "0":
        return
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env", override=False)


def playback() -> bool:
    return os.environ.get("DEMO_PLAYBACK", "false").lower() == "true"


def cache_dir() -> Path:
    return Path(os.environ.get("LLM_CACHE_DIR", BACKEND / "llm_cache"))


def cache_key(
    *,
    agent: str,
    step: str,
    prompt_version: str,
    model: str,
    system: str,
    prompt: str,
    schema: type[BaseModel],
) -> str:
    payload = json.dumps(
        {"model": model, "system": system, "prompt": prompt, "schema": schema.model_json_schema()},
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{prompt_version}.{agent}.{step}.{digest}"


def _read_cache[T: BaseModel](key: str, schema: type[T]) -> T | None:
    path = cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    try:
        return schema.model_validate(json.loads(path.read_text(encoding="utf-8"))["response"])
    except (ValueError, KeyError, ValidationError) as err:
        log.warning("llm cache entry %s unreadable (%s); treating as a miss", key, err)
        return None


def _write_cache(key: str, request: dict[str, Any], response: BaseModel) -> None:
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    entry = {"cache_key": key, "request": request, "response": response.model_dump(mode="json")}
    # Search workers may record the same key at once: write aside, then swap in atomically.
    tmp = folder / f"{key}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(entry, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, folder / f"{key}.json")


def _client() -> Any:
    global _client_cache
    if _client_cache is None:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise LLMUnavailable("no ANTHROPIC_API_KEY (set it in backend/.env)")
        import anthropic

        _client_cache = anthropic.Anthropic(
            timeout=float(os.environ.get("LLM_TIMEOUT", 60)), max_retries=1
        )
    return _client_cache


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
    load_env()
    model = os.environ.get(model_env) or DEFAULT_MODELS.get(model_env, "claude-opus-5-5")
    key = cache_key(
        agent=agent,
        step=step,
        prompt_version=prompt_version,
        model=model,
        system=system,
        prompt=prompt,
        schema=schema,
    )
    if (hit := _read_cache(key, schema)) is not None:
        return hit
    if playback():
        log.warning("playback: no recording for %s", key)
        raise LLMUnavailable(f"playback: no recording for {agent}/{step}")

    import anthropic

    try:
        response = _client().beta.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APITimeoutError as err:
        raise LLMUnavailable(f"timed out: {err}") from err
    except anthropic.AuthenticationError as err:
        raise LLMUnavailable(f"API key rejected: {err.message}") from err
    except anthropic.APIStatusError as err:
        raise LLMUnavailable(f"API error {err.status_code}: {err.message}") from err
    except anthropic.APIConnectionError as err:
        raise LLMUnavailable(f"connection failed: {err}") from err
    except ValidationError as err:
        raise LLMUnavailable(f"reply didn't fit {schema.__name__}: {err}") from err

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise LLMUnavailable(f"refused ({category})")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise LLMUnavailable(f"no structured reply (stop_reason={response.stop_reason})")

    reply = response.parsed_output
    _write_cache(key, {"model": response.model, "system": system, "prompt": prompt}, reply)
    return reply
