"""R12: persistence. SQLAlchemy Core tables (DESIGN 15) behind DATABASE_URL.

  DATABASE_URL=sqlite:///./vandal.db                     the fallback; also the default
  DATABASE_URL=postgresql+psycopg://...                   Supabase (session pooler)

The engine runs in memory; persistence only records. Events are written in batches by an
EventWriter, which is the sink a Run calls for every event (twin/world.Run). A run can always be
rebuilt from its persisted events: fold them over the seed and the state_hash matches.

Events are append-only in the database too. SQLite gets triggers when the tables are created;
Postgres gets migrations/0001_init.sql (RLS on with no policies, and a trigger that rejects
UPDATE and DELETE on events). Apply it with `Store.migrate()`.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    event,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from vandal.contracts.events import Event
from vandal.twin.profile import load_profile
from vandal.twin.reducer import fold
from vandal.twin.seed import seed_state
from vandal.twin.state import State

DEFAULT_URL = "sqlite:///./vandal.db"
MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
BATCH = 500

Json = JSON().with_variant(JSONB(), "postgresql")
# Event payloads stay `json` on Postgres, not `jsonb`: jsonb reorders object keys, and an event's
# serialized form (key order included) is part of state_hash, the replay identity.
ExactJson = JSON()
metadata = MetaData()


def _now() -> datetime:
    return datetime.now(UTC)


runs = Table(
    "runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, nullable=False),  # operate | replay | search | synth | verify
    Column("parent", String),
    Column("profile", String, nullable=False),
    Column("policy", String, nullable=False),
    Column("scenario", String),
    Column("seed", Integer, nullable=False),
    Column("summary", Json, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_now),
)

events = Table(
    "events",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("seq", Integer, primary_key=True),
    Column("id", String, nullable=False),
    Column("day", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("actor", String, nullable=False),
    Column("payload", ExactJson, nullable=False),
    Column("caused_by", ExactJson, nullable=False),
    Column("corrects", String),
)

policies = Table(
    "policies",
    metadata,
    Column("version", String, primary_key=True),
    Column("parent", String),
    Column("controls", Json, nullable=False),
    Column("diff", Json, nullable=False),
    Column("approval", Json),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_now),
)

searches = Table(
    "searches",
    metadata,
    Column("id", String, primary_key=True),
    Column("policy", String, nullable=False),
    Column("scenario", String, nullable=False),
    Column("alphabet", Integer, nullable=False),
    Column("depth", Integer, nullable=False),
    Column("explored", Integer, nullable=False),
    Column("violations", Integer, nullable=False),
    Column("minimal_trace", Json),
    Column("duration_ms", Integer, nullable=False),
)

syntheses = Table(
    "syntheses",
    metadata,
    Column("id", String, primary_key=True),
    Column("gap", String),
    Column("status", String, nullable=False),
    Column("iterations", Json, nullable=False),
    Column("candidates", Json, nullable=False),
    Column("chosen", Json, nullable=False),
    Column("scores", Json, nullable=False),
)

evidence_packs = Table(
    "evidence_packs",
    metadata,
    Column("id", String, primary_key=True),
    Column("synthesis", String),
    Column("contents", Json, nullable=False),
)

llm_calls = Table(
    "llm_calls",
    metadata,
    Column("cache_key", String, primary_key=True),
    Column("request", Json, nullable=False),
    Column("response", Json, nullable=False),
)

SQLITE_APPEND_ONLY = [
    "CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events "
    "BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Store:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("DATABASE_URL", DEFAULT_URL)
        self.engine: Engine = create_engine(self.url, future=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", _sqlite_pragmas)

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def migrate(self) -> None:
        """Create the tables, and make events append-only at the database."""
        if self.dialect == "postgresql":
            sql = (MIGRATIONS / "0001_init.sql").read_text()
            # Straight to the driver with no parameters, so the `%` in the trigger's message isn't
            # read as a placeholder.
            with self.engine.begin() as conn:
                conn.connection.driver_connection.execute(sql)
            return
        metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            for stmt in SQLITE_APPEND_ONLY:
                conn.execute(text(stmt))

    # --- runs and events --------------------------------------------------------------------

    def create_run(
        self,
        *,
        kind: str,
        profile: str,
        policy: str,
        seed: int,
        scenario: str | None = None,
        parent: str | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or new_id("run")
        with self.engine.begin() as conn:
            conn.execute(
                insert(runs).values(
                    id=run_id,
                    kind=kind,
                    parent=parent,
                    profile=profile,
                    policy=policy,
                    scenario=scenario,
                    seed=seed,
                    summary={},
                    created_at=_now(),
                )
            )
        return run_id

    def finish_run(self, run_id: str, summary: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(runs.update().where(runs.c.id == run_id).values(summary=summary))

    def writer(self, run_id: str, batch: int = BATCH) -> EventWriter:
        return EventWriter(self, run_id, batch)

    def events(self, run_id: str) -> list[Event]:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(select(events).where(events.c.run_id == run_id).order_by(events.c.seq))
                .mappings()
                .all()
            )
        return [
            Event.model_validate({k: v for k, v in row.items() if k != "run_id"}) for row in rows
        ]

    def run_row(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
        return dict(row)

    def rebuild(self, run_id: str) -> State:
        """The run's state, from its seed and its persisted events alone."""
        row = self.run_row(run_id)
        base = seed_state(load_profile(row["profile"]), seed=row["seed"])
        return fold(base, self.events(run_id))

    # --- results ----------------------------------------------------------------------------

    def save_policy(self, policy, approval: dict | None = None) -> None:
        # Keyed by version: applying the same synthesized version again after a Reset (the
        # demo loop run twice in one server) replaces the row instead of failing on the key.
        with self.engine.begin() as conn:
            conn.execute(delete(policies).where(policies.c.version == policy.version))
            conn.execute(
                insert(policies).values(
                    version=policy.version,
                    parent=policy.parent,
                    controls=[c.model_dump(mode="json") for c in policy.controls],
                    diff=list(policy.diff),
                    approval=approval,
                    created_at=_now(),
                )
            )

    def save_search(self, result, policy: str) -> str:
        sid = new_id("search")
        with self.engine.begin() as conn:
            conn.execute(
                insert(searches).values(
                    id=sid,
                    policy=policy,
                    scenario=result.scenario,
                    alphabet=result.alphabet,
                    depth=result.depth,
                    explored=result.explored,
                    violations=len(result.findings),
                    minimal_trace=(result.best.model_dump(mode="json") if result.best else None),
                    duration_ms=int(result.seconds * 1000),
                )
            )
        return sid

    def save_synthesis(self, result) -> str:
        sid = new_id("synth")
        log = [e.model_dump(mode="json") for e in result.log]
        with self.engine.begin() as conn:
            conn.execute(
                insert(syntheses).values(
                    id=sid,
                    gap=log[0]["gap"] if log else None,
                    status=result.status,
                    iterations=log,
                    candidates=[e["candidate"] for e in log],
                    chosen=list(result.chosen),
                    scores={e["candidate"]: e["score"] for e in log},
                )
            )
        return sid

    def save_evidence_pack(self, pack, synthesis: str | None = None) -> str:
        # Same as save_policy: verifying the same version twice replaces the pack.
        with self.engine.begin() as conn:
            conn.execute(delete(evidence_packs).where(evidence_packs.c.id == pack.version))
            conn.execute(
                insert(evidence_packs).values(
                    id=pack.version, synthesis=synthesis, contents=pack.model_dump(mode="json")
                )
            )
        return pack.version


class EventWriter:
    """A Run's sink: buffers events and inserts them in batches."""

    def __init__(self, store: Store, run_id: str, batch: int = BATCH) -> None:
        self.store = store
        self.run_id = run_id
        self.batch = batch
        self.buffer: list[dict[str, Any]] = []
        self.written = 0

    def __call__(self, ev: Event) -> None:
        self.buffer.append({"run_id": self.run_id, **ev.model_dump(mode="json")})
        if len(self.buffer) >= self.batch:
            self.flush()

    def flush(self) -> None:
        if not self.buffer:
            return
        with self.store.engine.begin() as conn:
            conn.execute(insert(events), self.buffer)
        self.written += len(self.buffer)
        self.buffer = []

    def __enter__(self) -> EventWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.flush()


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()
