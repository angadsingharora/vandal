"""A0: the in-memory run registry, and background jobs for long work.

A run is one live sandbox (a company under a policy). Every event it emits goes to its Channel
(for SSE) and, when a Store is configured, to the database in batches. A run's lock serializes
writers (operate) with readers (state, chain), since operate runs on a worker thread.

A job is long work (operate, search, synthesis, verification) on a thread pool. It publishes
progress to its own Channel and ends with a `done` or `error` message. A host can bound how
many run at once (`max_jobs`; past it `submit` raises JobsBusy, which the API answers with a
429), and finished jobs are kept to the newest `keep_finished` so a long-lived server stays
small.

A public host serves many visitors from one process. Runs and jobs carry the `owner` that made
them (api/deps.client): a reset drops one owner's runs and leaves everyone else's, `max_runs`
bounds the runs kept (the least recently touched go first), and `jobs_per_owner` keeps one
visitor from filling the pool.
"""

from __future__ import annotations

import itertools
import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from vandal.api.db import EventWriter, Store
from vandal.api.sse import Channel
from vandal.contracts.entities import OracleLabel
from vandal.contracts.events import Event
from vandal.guard.approvals import PolicyInbox
from vandal.sandbox import Sandbox, new_sandbox
from vandal.synth.templates import Policy


def verdict_summary(ev: Event) -> dict[str, Any]:
    """What the verdict feed shows: who asked for what, what Blue decided, and why."""
    v = ev.payload["verdict"]
    facts = v["facts"]
    return {
        "seq": ev.seq,
        "day": ev.day,
        "event": ev.id,
        "actor": ev.actor,
        "tool": ev.payload["tool"],
        "stage": ev.payload["stage"],
        "args": ev.payload["args"],
        "decision": v["decision"],
        "fired": v["fired"],
        "cites": v["cites"],
        "requires": facts.get("gate.requires", []),
        "cleared_by": facts.get("gate.cleared_evidence", []),
        "chain": {k.split(".", 1)[1]: val for k, val in facts.items() if k.startswith("chain.")},
    }


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# Orders runs by last use. A counter, not a clock: a clock's resolution can make two uses in
# the same tick look simultaneous.
_CLOCK = itertools.count(1)


class JobsBusy(RuntimeError):
    """The host's job limit is reached; try again shortly."""


@dataclass
class RunHandle:
    id: str
    profile: str
    seed: int
    policy: Policy
    sandbox: Sandbox
    channel: Channel
    verdicts: Channel = field(default_factory=Channel)  # B4: Blue's feed of decisions
    writer: EventWriter | None = None
    labels: list[OracleLabel] = field(default_factory=list)  # answer key of a replayed trace
    lock: threading.RLock = field(default_factory=threading.RLock)
    kind: str = "operate"
    owner: str | None = None  # the client that made it; None for a bare API call
    touched: int = field(default_factory=lambda: next(_CLOCK))  # last use, for eviction

    def touch(self) -> None:
        self.touched = next(_CLOCK)

    @property
    def state(self):
        return self.sandbox.run.state


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | done | failed
    result: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # what the job was asked to do
    channel: Channel = field(default_factory=Channel)
    owner: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "error": self.error,
            "meta": self.meta,
            "messages": len(self.channel),
        }


class Registry:
    def __init__(
        self,
        store: Store | None = None,
        threads: int = 4,
        max_jobs: int = 0,
        keep_finished: int = 200,
        max_runs: int = 0,
        jobs_per_owner: int = 0,
    ) -> None:
        self.store = store
        self.max_jobs = max_jobs  # 0: unlimited
        self.jobs_per_owner = jobs_per_owner  # 0: unlimited
        self.max_runs = max_runs  # 0: unlimited
        self.keep_finished = keep_finished
        self.runs: dict[str, RunHandle] = {}
        self.jobs: dict[str, Job] = {}
        self.inbox = PolicyInbox()  # B3: policy patches wait here for a human
        self.applied: dict[str, Policy] = {}  # policies applied through the inbox
        self.pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="vandal-job")

    # --- runs -------------------------------------------------------------------------------

    def create_run(
        self,
        profile: str,
        seed: int,
        policy: Policy,
        kind: str = "operate",
        owner: str | None = None,
    ) -> RunHandle:
        self._evict_runs(keep=1)
        run_id = _id("run")
        channel = Channel()
        writer = None
        if self.store is not None:
            self.store.create_run(
                kind=kind, profile=profile, policy=policy.version, seed=seed, run_id=run_id
            )
            writer = self.store.writer(run_id)

        verdicts = Channel()

        def sink(ev: Event) -> None:
            channel.publish("event", ev.model_dump(mode="json"))
            if ev.kind == "gate.verdict":
                verdicts.publish("verdict", verdict_summary(ev))
            elif ev.kind == "guard.alert":
                verdicts.publish("alert", {"seq": ev.seq, "day": ev.day, **ev.payload})
            if writer is not None:
                writer(ev)

        sb = new_sandbox(
            profile,
            seed=seed,
            policy=policy,
            sink=sink,
            monitor=True,
            # Live runs let intake ask Claude; replays stay on the reader search used.
            use_llm=kind == "operate",
        )
        handle = RunHandle(
            run_id, profile, seed, policy, sb, channel, verdicts, writer, kind=kind, owner=owner
        )
        self.runs[run_id] = handle
        return handle

    def run(self, run_id: str) -> RunHandle:
        handle = self.runs[run_id]
        handle.touch()
        return handle

    def runs_of(self, owner: str | None) -> list[RunHandle]:
        """An owner's runs, oldest first. None: every run (a bare API client sees it all)."""
        return [h for h in self.runs.values() if owner is None or h.owner == owner]

    def _drop(self, run_id: str) -> None:
        handle = self.runs.pop(run_id)
        handle.channel.close()
        handle.verdicts.close()
        if handle.writer is not None:
            handle.writer.flush()

    def _evict_runs(self, keep: int = 0) -> None:
        """Make room for `keep` more runs: past `max_runs`, the least recently touched go."""
        if not self.max_runs:
            return
        over = len(self.runs) + keep - self.max_runs
        if over <= 0:
            return
        for run_id in sorted(self.runs, key=lambda r: self.runs[r].touched)[:over]:
            self._drop(run_id)

    def reset(self, owner: str | None = None) -> None:
        """Drop an owner's runs; with no owner, every run."""
        for run_id in [h.id for h in self.runs_of(owner)]:
            self._drop(run_id)

    # --- jobs -------------------------------------------------------------------------------

    def active(self, owner: str | None = None) -> int:
        return sum(
            1
            for j in self.jobs.values()
            if j.status in ("queued", "running") and (owner is None or j.owner == owner)
        )

    def _evict_finished(self) -> None:
        finished = [j.id for j in self.jobs.values() if j.status in ("done", "failed")]
        for job_id in finished[: max(0, len(finished) - self.keep_finished)]:
            del self.jobs[job_id]

    def submit(
        self, kind: str, work: Callable[[Job], Any], owner: str | None = None, **meta: Any
    ) -> Job:
        if self.max_jobs and self.active() >= self.max_jobs:
            raise JobsBusy(
                f"the demo is busy: {self.active()} of {self.max_jobs} jobs running; "
                "try again in a minute"
            )
        if owner and self.jobs_per_owner and self.active(owner) >= self.jobs_per_owner:
            raise JobsBusy(
                f"you already have {self.active(owner)} job(s) running; wait for them to finish"
            )
        self._evict_finished()
        job = Job(id=_id(kind), kind=kind, meta=meta, owner=owner)
        self.jobs[job.id] = job

        def runner() -> None:
            job.status = "running"
            job.channel.publish("status", {"status": "running"})
            try:
                job.result = work(job)
                job.status = "done"
                job.channel.publish("done", {"status": "done"})
            except Exception as err:  # the job fails, the server doesn't
                job.status = "failed"
                job.error = f"{type(err).__name__}: {err}"
                job.channel.publish(
                    "error", {"error": job.error, "trace": traceback.format_exc(limit=5)}
                )
            finally:
                job.channel.close()

        self.pool.submit(runner)
        return job

    def job(self, job_id: str) -> Job:
        return self.jobs[job_id]

    def shutdown(self) -> None:
        self.reset()
        self.pool.shutdown(wait=False, cancel_futures=True)
