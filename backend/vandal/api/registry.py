"""A0: the in-memory run registry, and background jobs for long work.

A run is one live sandbox (a company under a policy). Every event it emits goes to its Channel
(for SSE) and, when a Store is configured, to the database in batches. A run's lock serializes
writers (operate) with readers (state, chain), since operate runs on a worker thread.

A job is long work (operate, search, synthesis, verification) on a thread pool. It publishes
progress to its own Channel and ends with a `done` or `error` message.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from vandal.api.db import EventWriter, Store
from vandal.api.sse import Channel
from vandal.contracts.events import Event
from vandal.sandbox import Sandbox, new_sandbox
from vandal.synth.templates import Policy


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@dataclass
class RunHandle:
    id: str
    profile: str
    seed: int
    policy: Policy
    sandbox: Sandbox
    channel: Channel
    writer: EventWriter | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

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
    def __init__(self, store: Store | None = None, threads: int = 4) -> None:
        self.store = store
        self.runs: dict[str, RunHandle] = {}
        self.jobs: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="vandal-job")

    # --- runs -------------------------------------------------------------------------------

    def create_run(
        self, profile: str, seed: int, policy: Policy, kind: str = "operate"
    ) -> RunHandle:
        run_id = _id("run")
        channel = Channel()
        writer = None
        if self.store is not None:
            self.store.create_run(
                kind=kind, profile=profile, policy=policy.version, seed=seed, run_id=run_id
            )
            writer = self.store.writer(run_id)

        def sink(ev: Event) -> None:
            channel.publish("event", ev.model_dump(mode="json"))
            if writer is not None:
                writer(ev)

        sb = new_sandbox(profile, seed=seed, policy=policy, sink=sink)
        handle = RunHandle(run_id, profile, seed, policy, sb, channel, writer)
        self.runs[run_id] = handle
        return handle

    def run(self, run_id: str) -> RunHandle:
        return self.runs[run_id]

    def reset(self) -> None:
        for handle in self.runs.values():
            handle.channel.close()
            if handle.writer is not None:
                handle.writer.flush()
        self.runs.clear()

    # --- jobs -------------------------------------------------------------------------------

    def submit(self, kind: str, work: Callable[[Job], Any], **meta: Any) -> Job:
        job = Job(id=_id(kind), kind=kind, meta=meta)
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
