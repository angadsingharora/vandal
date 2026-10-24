"""R12 done-when: a run rebuilt from its persisted events gives the same state_hash, an UPDATE on
events fails, and the app still runs with SQLite. The Postgres tests run when
VANDAL_TEST_DATABASE_URL points at one (they create and drop their own tables' rows by run id)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from vandal.api.db import Store, new_id
from vandal.cli import main
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.templates import Policy

PG_URL = os.environ.get("VANDAL_TEST_DATABASE_URL")
BACKENDS = ["sqlite"] + (["postgres"] if PG_URL else [])


@pytest.fixture(params=BACKENDS)
def store(request, tmp_path):
    url = f"sqlite:///{tmp_path / 'vandal.db'}" if request.param == "sqlite" else PG_URL
    s = Store(url)
    s.migrate()
    s.migrate()  # idempotent
    return s


def persisted_run(store: Store, days: int = 3, batch: int = 500):
    run_id = store.create_run(kind="operate", profile="bayline", policy="v0", seed=7)
    with store.writer(run_id, batch=batch) as writer:
        sb = new_sandbox(sink=writer).operate(days)
    state = sb.run.state
    store.finish_run(run_id, {"state_hash": state.state_hash()})
    return run_id, state, writer


def test_rebuilt_run_has_the_same_hash(store) -> None:
    run_id, state, writer = persisted_run(store)
    assert writer.written == len(state.events) > 0
    rebuilt = store.rebuild(run_id)
    assert rebuilt.state_hash() == state.state_hash()
    assert store.run_row(run_id)["summary"]["state_hash"] == state.state_hash()


@pytest.mark.parametrize(
    "sql",
    [
        "update events set kind = 'tampered' where run_id = :r",
        "delete from events where run_id = :r",
    ],
)
def test_events_are_append_only_in_the_database(store, sql) -> None:
    run_id, _, _ = persisted_run(store, days=1)
    with pytest.raises(DBAPIError, match="append-only"), store.engine.begin() as conn:
        conn.execute(text(sql), {"r": run_id})
    assert len(store.events(run_id)) > 0


def test_events_are_written_in_batches(store) -> None:
    run_id = store.create_run(kind="operate", profile="bayline", policy="v0", seed=7)
    writer = store.writer(run_id, batch=50)
    flushes = []
    real = writer.flush

    def counting_flush():
        flushes.append(len(writer.buffer))
        real()

    writer.flush = counting_flush
    sb = new_sandbox(sink=writer).operate(1)
    writer.flush()
    assert sum(flushes) == len(sb.run.state.events)
    assert max(flushes) == 50 and len(flushes) > 1


def test_results_are_saved(store) -> None:
    v1 = Policy.load("policies/v1.json")
    v1 = v1.model_copy(update={"version": new_id("v1-test")})  # reruns on one database
    store.save_policy(v1, approval={"by": "U-CTRL"})
    result = search(lambda s: new_sandbox(seed=s), SCENARIOS["a"], depth=1)
    sid = store.save_search(result, policy="v0")
    with store.engine.connect() as conn:
        row = conn.execute(
            text("select explored, violations from searches where id = :i"), {"i": sid}
        ).one()
        diff = conn.execute(
            text("select diff from policies where version = :v"), {"v": v1.version}
        ).scalar()
    assert tuple(row) == (result.explored, len(result.findings))
    assert diff == v1.diff or diff == str(v1.diff)  # jsonb or json text, depending on driver


def test_database_url_comes_from_the_environment(monkeypatch, tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'env.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    assert Store().url == url and Store().dialect == "sqlite"


def test_run_persist_and_rebuild_cli(tmp_path, capsys) -> None:
    db = f"sqlite:///{tmp_path / 'cli.db'}"
    assert main(["run", "--days", "2", "--persist", "--db", db]) == 0
    out = capsys.readouterr().out
    run_id = next(line.split()[1] for line in out.splitlines() if "persisted" in line)
    assert main(["rebuild", run_id, "--db", db]) == 0
    assert "identical" in capsys.readouterr().out


def test_saving_the_same_version_twice_replaces_it(store) -> None:
    """The demo loop run twice in one server: /verify and /policies/{v}/apply save the same
    version again, which must replace the row, not fail on the primary key."""
    from vandal.verify.evidence_pack import EvidencePack

    v = Policy.load("policies/v1.json").model_copy(update={"version": new_id("v1-twice")})
    store.save_policy(v, approval={"by": "U-CTRL"})
    store.save_policy(v, approval={"by": "U-CFO"})
    pack = EvidencePack.model_construct(version=v.version)
    store.save_evidence_pack(pack, synthesis="synth-1")
    store.save_evidence_pack(pack, synthesis="synth-2")
    with store.engine.connect() as conn:
        n_pol = conn.execute(
            text("select count(*) from policies where version = :v"), {"v": v.version}
        ).scalar()
        syn = conn.execute(
            text("select synthesis from evidence_packs where id = :v"), {"v": v.version}
        ).all()
    assert n_pol == 1 and syn == [("synth-2",)]
