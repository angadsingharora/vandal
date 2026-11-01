"""Hosted limits for the public API.

A demo host (Render's free tier) has a fraction of a CPU, and anyone with the URL can start a
job. These caps keep one visitor from pinning it for everyone else:

  - VANDAL_MAX_DEPTH and VANDAL_MAX_WORKERS clamp what a request may ask for. The job's meta
    records the depth it actually ran at, and `clamped` when that differs from the request.
  - VANDAL_MAX_JOBS bounds the jobs queued or running at once; past it the API answers 429
    with a Retry-After, and the war room says the demo is busy.
  - VANDAL_JOBS_PER_CLIENT bounds the jobs one visitor (api/deps.client) may have queued or
    running, so one tab can't take the whole pool.
  - VANDAL_MAX_RUNS bounds the runs kept in memory; past it the least recently touched runs
    are dropped (api/registry.py), so a long-lived host stays small.
  - SEARCH_WORKERS is the worker count a request gets when it doesn't name one.

Unset, nothing is limited, which is right for a laptop. /settings reports the limits so the
war room offers only what the host can do.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

MAX_DEPTH = 6
MAX_WORKERS = 32


@dataclass(frozen=True)
class Limits:
    max_depth: int = MAX_DEPTH
    max_workers: int = MAX_WORKERS
    max_jobs: int = 0  # 0: unlimited
    jobs_per_client: int = 0  # 0: unlimited
    max_runs: int = 0  # 0: unlimited
    default_workers: int = 1

    def depth(self, asked: int) -> int:
        return min(asked, self.max_depth)

    def workers(self, asked: int | None) -> int:
        return min(asked or self.default_workers, self.max_workers)

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def limits() -> Limits:
    """The host's limits, read from the environment on every call (tests change them at
    runtime)."""
    return Limits(
        max_depth=max(1, min(MAX_DEPTH, _int("VANDAL_MAX_DEPTH", MAX_DEPTH))),
        max_workers=max(1, min(MAX_WORKERS, _int("VANDAL_MAX_WORKERS", MAX_WORKERS))),
        max_jobs=max(0, _int("VANDAL_MAX_JOBS", 0)),
        jobs_per_client=max(0, _int("VANDAL_JOBS_PER_CLIENT", 0)),
        max_runs=max(0, _int("VANDAL_MAX_RUNS", 0)),
        default_workers=max(1, min(MAX_WORKERS, _int("SEARCH_WORKERS", 1))),
    )
