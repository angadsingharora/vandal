"""Recorded jobs: search, synthesis, and verification results replayed from disk.

The twin is deterministic: the same profile, seed, policy, scenario, and depth give the same
result every time, and the model calls inside synthesis already replay from llm_cache. So a
finished job can be recorded as one JSON file under JOB_CACHE_DIR (default backend/job_cache/)
and served again without the minutes of search, which is what a demo on a small host needs.

  - Every computed job is recorded. A recording is never written back on a hit.
  - A recording is served only when playback is on (DEMO_PLAYBACK, the top bar's switch) and
    the request didn't ask for `fresh`. Playback off always computes, so development never
    sees a stale result.
  - The key is CACHE_VERSION plus a hash of everything the result depends on. Bump
    CACHE_VERSION when search, synthesis, or verification change what they produce.
  - A served result carries `cached: true` and `recorded_at`, and the war room says so.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vandal.llm import BACKEND, playback

log = logging.getLogger(__name__)

CACHE_VERSION = "jobs-v1"


def cache_dir() -> Path:
    return Path(os.environ.get("JOB_CACHE_DIR", BACKEND / "job_cache"))


def key(kind: str, inputs: dict[str, Any]) -> str:
    payload = json.dumps(inputs, sort_keys=True, default=str)
    return f"{CACHE_VERSION}.{kind}.{hashlib.sha256(payload.encode()).hexdigest()}"


def read(cache_key: str) -> dict[str, Any] | None:
    path = cache_dir() / f"{cache_key}.json"
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        return {"result": entry["result"], "recorded_at": entry.get("recorded_at")}
    except (ValueError, KeyError) as err:
        log.warning("job cache entry %s unreadable (%s); treating as a miss", cache_key, err)
        return None


def write(cache_key: str, kind: str, inputs: dict[str, Any], result: dict[str, Any]) -> None:
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    entry = {
        "cache_key": cache_key,
        "kind": kind,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inputs": inputs,
        "result": result,
    }
    tmp = folder / f"{cache_key}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(entry, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, folder / f"{cache_key}.json")


def serve(
    kind: str,
    inputs: dict[str, Any],
    compute: Callable[[], dict[str, Any]],
    *,
    fresh: bool = False,
    on_hit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """The recorded result when playback is on and one exists (after `on_hit`, which replays
    the messages the job would have streamed); otherwise compute, record, and return."""
    cache_key = key(kind, inputs)
    if playback() and not fresh:
        hit = read(cache_key)
        if hit is not None:
            if on_hit is not None:
                on_hit(hit["result"])
            return {**hit["result"], "cached": True, "recorded_at": hit["recorded_at"]}
    result = compute()
    try:
        write(cache_key, kind, inputs, result)
    except OSError as err:  # a read-only host still answers
        log.warning("job cache write failed (%s)", err)
    return {**result, "cached": False}
