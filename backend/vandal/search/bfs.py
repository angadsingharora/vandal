"""R4: breadth-first search over move sequences up to SEARCH_DEPTH, with state-hash dedup.

Each node is a sequence of alphabet moves. Running a node replays it from the seed state (one
"run"), which gives two things:

  key         (World position, entity_hash, oracle labels) right after the node's last move.
              Two sequences with the same key have the same future, so only the first is
              expanded (dedup).
  violations  the invariants broken once the World finishes.

Search stays sound and small with three rules:
- A violating node isn't expanded: anything longer is not a minimal counterexample.
- Sequences are canonical: `at` never decreases, and two adjacent independent moves at the same
  `at` appear only in alphabet order (partial-order reduction, search/alphabet.independent).
- Levels run in order and results are merged in order, so the output is the same for any
  number of workers.

search/ may not import operator/, so the caller passes a sandbox factory.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents
from vandal.contracts.moves import Move
from vandal.search.alphabet import Scenario, build_alphabet, independent
from vandal.twin.state import State
from vandal.twin.world import run_step, schedule
from vandal.verify.invariants import Limits, check, exposure
from vandal.verify.oracle import Oracle
from vandal.verify.replay import SandboxFactory, SandboxLike, apply_move

Key = tuple[int, str, tuple[tuple[str, str, str], ...]]
Seq = tuple[int, ...]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    moves: list[Move]
    violated: list[str]
    exposure: Cents


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    depth: int
    alphabet: int
    explored: int  # sequences run
    deduped: int  # runs whose state was already seen
    pruned: int  # canonical-order skips (partial-order reduction)
    levels: list[int]  # sequences run per depth
    findings: list[Finding]  # every violating sequence at the depth where violations appeared
    best: Finding | None
    seconds: float
    workers: int

    @property
    def ms_per_run(self) -> float:
        return 1000 * self.seconds / max(self.explored, 1)

    @property
    def runs_per_second(self) -> float:
        return self.explored / self.seconds if self.seconds else 0.0


# --- runs -----------------------------------------------------------------------------------


@dataclass
class Runner:
    """Runs move sequences against one sandbox.

    Children of one parent share the parent's prefix: the parent is replayed once, the World is
    advanced through each insertion point the children use, and each child starts from a
    snapshot of that point (clones share entities, so snapshots are cheap). A "run" is one child
    played from its insertion point to the end of the World, plus the invariant check.
    """

    sb: SandboxLike
    scenario: Scenario
    base: State = field(init=False)
    limits: Limits = field(init=False)

    def __post_init__(self) -> None:
        self.base = self.sb.run.state.clone()
        self.limits = Limits.from_profile(self.sb.profile)
        self.steps = schedule(self.scenario.days, start_day=self.base.day)

    def _step(self, index: int) -> None:
        sb = self.sb
        run_step(sb.run, sb.tools, self.steps[index], sb.operator, sb.approver)

    def _prefix(self, moves: Sequence[Move]) -> tuple[State, Oracle, int]:
        """State right after the last move (before World step `pos` runs)."""
        self.sb.run.state = self.base.clone()
        oracle = Oracle()
        pos = 0
        for i, move in enumerate(moves):
            while pos < move.at and pos < len(self.steps):
                self._step(pos)
                pos += 1
            apply_move(self.sb, move, i, oracle)
        return self.sb.run.state, oracle, pos

    def _finish(self, pos: int, oracle: Oracle) -> tuple[Key, list[str], Cents]:
        key = (pos, self.sb.run.state.entity_hash(), _labels(oracle))
        for index in range(pos, len(self.steps)):
            self._step(index)
        violations = check(self.sb.run.state, oracle, self.limits)
        return key, sorted({v.invariant for v in violations}), exposure(violations)

    def run(self, moves: Sequence[Move]) -> tuple[Key, list[str], Cents]:
        _, oracle, pos = self._prefix(moves)
        return self._finish(pos, oracle)

    def run_children(
        self, parent: Sequence[Move], children: Sequence[Move]
    ) -> list[tuple[Key, list[str], Cents]]:
        """Run parent + [child] for each child. Children must be sorted by `at`, all at or after
        the parent's position."""
        state, oracle, pos = self._prefix(parent)
        snapshots: dict[int, State] = {}
        cursor = state.clone()
        for at in sorted({c.at for c in children}):
            self.sb.run.state = cursor
            while pos < at and pos < len(self.steps):
                self._step(pos)
                pos += 1
            snapshots[at] = cursor.clone()
        out = []
        index = len(parent)
        for child in children:
            self.sb.run.state = snapshots[child.at].clone()
            child_oracle = Oracle()
            child_oracle.labels = list(oracle.labels)
            apply_move(self.sb, child, index, child_oracle)
            out.append(self._finish(min(child.at, len(self.steps)), child_oracle))
        return out


def _labels(oracle: Oracle) -> tuple[tuple[str, str, str], ...]:
    return tuple(sorted((lb.subject, lb.label, str(lb.value)) for lb in oracle.labels))


# --- workers --------------------------------------------------------------------------------

_WORKER: tuple[Runner, list[Move]] | None = None


def _init_worker(factory: SandboxFactory, seed: int, scenario: Scenario) -> None:
    global _WORKER
    sb = factory(seed)
    runner = Runner(sb, scenario)
    _WORKER = (runner, build_alphabet(scenario, runner.base, sb.profile))


def _expand(runner: Runner, alphabet: list[Move], task: tuple[Seq, list[Seq]]):
    parent, children = task
    results = runner.run_children(
        [alphabet[j] for j in parent], [alphabet[c[-1]] for c in children]
    )
    return [(c, *r) for c, r in zip(children, results, strict=True)]


def _expand_in_worker(task: tuple[Seq, list[Seq]]):
    assert _WORKER is not None
    return _expand(*_WORKER, task)


# --- search ---------------------------------------------------------------------------------


def canonical_children(seq: Seq, alphabet: list[Move]) -> tuple[list[Seq], int]:
    """Children of `seq` that respect canonical order, and how many were skipped."""
    out: list[Seq] = []
    skipped = 0
    prev = alphabet[seq[-1]] if seq else None
    for j, move in enumerate(alphabet):
        if prev is not None:
            if move.at < prev.at:
                continue  # timing order is part of the sequence, not a reduction
            if move.at == prev.at and j < seq[-1] and independent(prev, move):
                skipped += 1
                continue
        out.append(seq + (j,))
    return out, skipped


def rank(f: Finding) -> tuple:
    """Most exposure first, then the most invariants broken, then the shortest, then the latest
    timing (an attacker acting as close to execution as possible)."""
    return (-f.exposure, -len(f.violated), len(f.moves), -sum(m.at for m in f.moves))


def search(
    factory: SandboxFactory,
    scenario: Scenario,
    *,
    seed: int = 7,
    depth: int = 4,
    workers: int = 1,
    exhaustive: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> SearchResult:
    """Explore every canonical sequence up to `depth`. Without `exhaustive`, stop after the
    first depth that has violations: those are the minimal counterexamples."""
    started = time.perf_counter()
    local = Runner(factory(seed), scenario)
    alphabet = build_alphabet(scenario, local.base, local.sb.profile)

    pool = None
    if workers > 1:
        ctx = mp.get_context("spawn")
        pool = ctx.Pool(workers, initializer=_init_worker, initargs=(factory, seed, scenario))

    def run_all(tasks: list[tuple[Seq, list[Seq]]]) -> Iterator[tuple[Seq, Key, list[str], Cents]]:
        """Results in task order, whatever the number of workers."""
        if pool is None:
            for task in tasks:
                yield from _expand(local, alphabet, task)
        else:
            chunk = max(1, len(tasks) // (workers * 8))
            for batch in pool.imap(_expand_in_worker, tasks, chunksize=chunk):
                yield from batch

    explored = deduped = pruned = 0
    levels: list[int] = []
    findings: list[Finding] = []
    seen: set[Key] = set()
    try:
        root_key, root_violated, root_exposure = local.run([])
        seen.add(root_key)
        if root_violated:
            findings.append(Finding(moves=[], violated=root_violated, exposure=root_exposure))
        frontier: list[Seq] = [()]
        for d in range(1, depth + 1):
            if findings and not exhaustive:
                break
            tasks: list[tuple[Seq, list[Seq]]] = []
            for seq in frontier:
                children, skipped = canonical_children(seq, alphabet)
                pruned += skipped
                if children:
                    tasks.append((seq, children))
            candidates = sum(len(c) for _, c in tasks)
            next_frontier: list[Seq] = []
            for seq, key, violated, exp in run_all(tasks):
                explored += 1
                if progress and explored % 1000 == 0:
                    progress(d, explored)
                if key in seen:
                    deduped += 1
                    continue
                seen.add(key)
                if violated:
                    findings.append(
                        Finding(moves=[alphabet[j] for j in seq], violated=violated, exposure=exp)
                    )
                else:
                    next_frontier.append(seq)
            levels.append(candidates)
            frontier = next_frontier
            if not frontier:
                break
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    return SearchResult(
        scenario=scenario.name,
        depth=depth,
        alphabet=len(alphabet),
        explored=explored,
        deduped=deduped,
        pruned=pruned,
        levels=levels,
        findings=findings,
        best=min(findings, key=rank) if findings else None,
        seconds=time.perf_counter() - started,
        workers=workers,
    )
