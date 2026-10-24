-- R12: Vandal's tables on Postgres (Supabase). Mirrors vandal/api/db.py.
-- RLS is on with no policies: only the service connection the backend uses can read or write.
-- Events are append-only: a trigger rejects UPDATE and DELETE.

create table if not exists runs (
    id          text primary key,
    kind        text not null,
    parent      text,
    profile     text not null,
    policy      text not null,
    scenario    text,
    seed        integer not null,
    summary     jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create table if not exists events (
    run_id     text not null,
    seq        integer not null,
    id         text not null,
    day        integer not null,
    kind       text not null,
    actor      text not null,
    payload    json not null,   -- json, not jsonb: key order is part of the replay hash
    caused_by  json not null,
    corrects   text,
    primary key (run_id, seq)
);

create table if not exists policies (
    version     text primary key,
    parent      text,
    controls    jsonb not null,
    diff        jsonb not null,
    approval    jsonb,
    created_at  timestamptz not null default now()
);

create table if not exists searches (
    id             text primary key,
    policy         text not null,
    scenario       text not null,
    alphabet       integer not null,
    depth          integer not null,
    explored       integer not null,
    violations     integer not null,
    minimal_trace  jsonb,
    duration_ms    integer not null
);

create table if not exists syntheses (
    id          text primary key,
    gap         text,
    status      text not null,
    iterations  jsonb not null,
    candidates  jsonb not null,
    chosen      jsonb not null,
    scores      jsonb not null
);

create table if not exists evidence_packs (
    id         text primary key,
    synthesis  text,
    contents   jsonb not null
);

create table if not exists llm_calls (
    cache_key  text primary key,
    request    jsonb not null,
    response   jsonb not null
);

alter table runs           enable row level security;
alter table events         enable row level security;
alter table policies       enable row level security;
alter table searches       enable row level security;
alter table syntheses      enable row level security;
alter table evidence_packs enable row level security;
alter table llm_calls      enable row level security;

create or replace function events_append_only() returns trigger
language plpgsql as $$
begin
    raise exception 'events are append-only (% rejected)', tg_op;
end;
$$;

drop trigger if exists events_append_only on events;
create trigger events_append_only
    before update or delete on events
    for each row execute function events_append_only();
