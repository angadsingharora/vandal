"""A0 routes for runs: create, operate, read state and entities, stream events, replay (R1, R2,
R3, R5)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.api.registry import RunHandle
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.synth.coverage import build_chain
from vandal.twin.world import run_step, schedule, settle
from vandal.verify.invariants import Limits, check, exposure
from vandal.verify.messy import messy_items, reopen_as_message
from vandal.verify.oracle import Oracle
from vandal.verify.replay import replay_detailed

router = APIRouter()


class NewRun(BaseModel):
    profile: str = "bayline"
    seed: int = 7
    policy: str = "v0"


class Operate(BaseModel):
    days: int = Field(default=5, ge=1, le=90)


class Replay(BaseModel):
    moves: list[Move]
    labels: list[OracleLabel] = []
    days: int = Field(default=2, ge=1, le=30)
    profile: str = "bayline"
    seed: int = 7
    policy: str = "v0"


def _violations(handle: RunHandle):
    """Invariants on the run's state, with a replayed trace's answer key when it has one (INV-4
    needs to know which accounts the attacker controls)."""
    oracle = None
    if handle.labels:
        oracle = Oracle()
        oracle.labels.extend(handle.labels)
    return check(handle.state, oracle, Limits.from_profile(handle.sandbox.profile))


def summary(handle: RunHandle) -> dict[str, Any]:
    with handle.lock:
        state = handle.state
        violations = _violations(handle)
        return {
            "run_id": handle.id,
            "company": state.company,
            "profile": handle.profile,
            "seed": handle.seed,
            "policy": handle.policy.version,
            "day": state.day,
            "invoices": dict(Counter(i.status for i in state.invoices.values())),
            "payments": dict(Counter(p.status for p in state.payments.values())),
            "bank": {
                b.id: {"name": b.name, "balance": b.balance} for b in state.bank_accounts.values()
            },
            "open_approvals": sum(
                1 for r in state.approval_requests.values() if r.status == "pending"
            ),
            "change_requests": dict(Counter(c.status for c in state.change_requests.values())),
            "violations": [v.model_dump() for v in violations],
            "events": len(state.events),
            "state_hash": state.state_hash(),
        }


def _create(request: Request, body: NewRun) -> dict[str, Any]:
    handle = deps.registry(request).create_run(
        deps.profile_name(body.profile), body.seed, deps.policy(body.policy, request)
    )
    return summary(handle)


# --- O1: documents through the LLM Operator's intake -----------------------------------------


def _documents(handle: RunHandle):
    return messy_items(handle.state, handle.sandbox.profile)


@router.get("/runs/{run_id}/documents")
def documents(request: Request, run_id: str) -> list[dict[str, Any]]:
    """The planted messy documents (DESIGN 5.6) a run's company can receive: the pending
    invoices as the email bodies, OCR'd scans, forwarded threads, and line-item tables they
    arrived as. The answer key stays on the server."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        read = {m for m, _ in getattr(handle.sandbox.operator, "read", [])}
        return [
            {
                "id": it.id,
                "format": it.format,
                "channel": it.message.channel,
                "sender": it.message.sender,
                "subject": it.message.subject,
                "body": it.message.body,
                "invoice": it.truth.invoice,
                "delivered": it.id in read,
            }
            for it in _documents(handle)
        ]


@router.post("/runs/{run_id}/documents/{item_id}/deliver")
def deliver_document(request: Request, run_id: str, item_id: str) -> dict[str, Any]:
    """Make a planted document arrive: its structured copy leaves the twin and the Operator
    has to read the message. Returns what intake read and what Blue did with it."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        item = next((it for it in _documents(handle) if it.id == item_id), None)
        if item is None:
            raise HTTPException(404, f"no document {item_id}")
        sb = handle.sandbox
        if any(m == item_id for m, _ in sb.operator.read):
            raise HTTPException(409, f"{item_id} was already delivered")
        reopen_as_message(sb.run.state, item)
        sb.run.emit(
            "channel.received", {"message": item.message.model_dump(mode="json")}, actor="external"
        )
        before = len(sb.run.state.events)
        sb.operator.on_event(item.message, sb.tools)
        settle(sb.run, sb.tools, sb.operator, None)
        state = sb.run.state
        extraction = sb.operator.read[-1][1].model_dump() if sb.operator.read else None
        verdicts = [
            {"tool": e.payload["tool"], **e.payload["verdict"]}
            for e in state.events[before:]
            if e.kind == "gate.verdict"
        ]
        received = next(
            (
                i.model_dump()
                for i in state.invoices.values()
                if i.number == (extraction or {}).get("number")
            ),
            None,
        )
        if handle.writer is not None:
            handle.writer.flush()
    return {
        "document": item_id,
        "extraction": extraction,
        "verdicts": verdicts,
        "invoice": received,
    }


@router.get("/runs/{run_id}/intake")
def intake_reads(request: Request, run_id: str) -> list[dict[str, Any]]:
    """What the LLM Operator's intake read from each unstructured message, in order."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        return [
            {"message": m, **x.model_dump()}
            for m, x in getattr(handle.sandbox.operator, "read", [])
        ]


@router.post("/demo/reset")
def demo_reset(request: Request, body: NewRun | None = None) -> dict[str, Any]:
    """Drop every run and start one fresh company."""
    deps.registry(request).reset()
    return _create(request, body or NewRun())


@router.post("/runs")
def create_run(request: Request, body: NewRun | None = None) -> dict[str, Any]:
    return _create(request, body or NewRun())


@router.get("/runs")
def list_runs(request: Request) -> list[dict[str, Any]]:
    return [
        {
            "run_id": h.id,
            "policy": h.policy.version,
            "day": h.state.day,
            "events": len(h.state.events),
        }
        for h in deps.registry(request).runs.values()
    ]


@router.get("/runs/{run_id}/state")
def run_state(request: Request, run_id: str) -> dict[str, Any]:
    return summary(deps.get_run(request, run_id))


@router.get("/runs/{run_id}/ledger")
def run_ledger(request: Request, run_id: str) -> list[dict[str, Any]]:
    handle = deps.get_run(request, run_id)
    with handle.lock:
        return [je.model_dump(mode="json") for je in handle.state.journal]


@router.get("/runs/{run_id}/entities")
def run_entities(request: Request, run_id: str) -> dict[str, Any]:
    """The twin's tables for the war room (F1): invoices, payments with their instructions,
    vendors and their bank accounts, the bank feed, change requests, cases, and approvals.
    `labels` is the oracle's answer key for a replayed trace; only the Judge view shows it."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        state = handle.state

        def rows(table: dict) -> list[dict[str, Any]]:
            return [e.model_dump(mode="json") for e in table.values()]

        payments = []
        for p in state.payments.values():
            pi = state.payment_instructions.get(p.instruction)
            payments.append(
                p.model_dump(mode="json")
                | (
                    {"invoice": pi.invoice, "amount": pi.amount, "payee_account": pi.payee_account}
                    if pi
                    else {}
                )
            )
        violations = _violations(handle)
        open_ap = sum(
            i.amount
            for i in state.invoices.values()
            if i.kind == "invoice"
            and i.status in ("received", "validated", "approved", "scheduled", "held")
        )
        return {
            "run_id": handle.id,
            "day": state.day,
            "totals": {
                "cash": sum(b.balance for b in state.bank_accounts.values()),
                "open_ap": open_ap,
                "exposure": exposure(violations),
            },
            "vendors": rows(state.vendors),
            "vendor_bank_accounts": rows(state.vendor_bank_accounts),
            "invoices": rows(state.invoices),
            "payments": payments,
            "bank_accounts": rows(state.bank_accounts),
            "bank_transactions": rows(state.bank_transactions),
            "change_requests": rows(state.change_requests),
            "approval_requests": rows(state.approval_requests),
            "cases": rows(state.cases),
            "labels": [lb.model_dump(mode="json") for lb in handle.labels],
        }


@router.get("/runs/{run_id}/events")
def run_events(request: Request, run_id: str, start: int | None = None, follow: bool = True):
    """SSE: every event of the run from `start`, then live (`event: event` messages)."""
    return deps.sse(request, deps.get_run(request, run_id).channel, start, follow)


@router.post("/runs/{run_id}/operate")
def operate(request: Request, run_id: str, body: Operate | None = None) -> dict[str, Any]:
    """Run the World for `days` business days on a worker thread. Events stream on
    /runs/{id}/events; day-by-day progress on /jobs/{job}/events."""
    handle = deps.get_run(request, run_id)
    days = (body or Operate()).days

    def work(job) -> dict[str, Any]:
        sb = handle.sandbox
        with handle.lock:
            start = sb.run.state.day
            for step in schedule(days, start_day=start):
                run_step(sb.run, sb.tools, step, sb.operator, sb.approver)
                if step.kind == "tick":
                    job.channel.publish(
                        "progress", {"day": step.day + 1, "events": len(sb.run.state.events)}
                    )
            if handle.writer is not None:
                handle.writer.flush()
        return summary(handle)

    return deps.registry(request).submit("operate", work, run_id=run_id, days=days).summary()


@router.get("/runs/{run_id}/chain/{payment}")
def chain(request: Request, run_id: str, payment: str) -> dict[str, Any]:
    """The authorization chain for one payment (R5)."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        if payment not in handle.state.payments:
            raise HTTPException(404, f"no payment {payment} in {run_id}")
        return build_chain(
            handle.state, payment, Limits.from_profile(handle.sandbox.profile)
        ).model_dump(mode="json")


@router.post("/replay")
def replay(request: Request, body: Replay) -> dict[str, Any]:
    """Replay a trace on a fresh company as a new run; its events stream like any run's."""
    reg = deps.registry(request)
    policy = deps.policy(body.policy, request)
    handle = reg.create_run(deps.profile_name(body.profile), body.seed, policy, kind="replay")
    with handle.lock:
        result, _, oracle = replay_detailed(
            body.seed,
            body.moves,
            sandbox=lambda _seed: handle.sandbox,
            days=body.days,
            labels=body.labels,
        )
        handle.labels = list(oracle.labels)
        if handle.writer is not None:
            handle.writer.flush()
    return {
        "run": summary(handle),
        "result": {**result.model_dump(mode="json"), "violated": result.violated},
        "labels": [lb.model_dump(mode="json") for lb in handle.labels],
    }
