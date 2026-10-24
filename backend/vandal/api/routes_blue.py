"""Blue's routes: the verdict feed (B4), approvals and segregation of duties (B3), applying
policy patches (B3), and cited explanations (B5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from vandal.api import deps
from vandal.contracts.entities import Actor
from vandal.guard.approvals import InboxError
from vandal.guard.explain import explain_safely
from vandal.synth.templates import Policy
from vandal.twin.flows import DecideArgs

router = APIRouter()


class Decision(BaseModel):
    actor: Actor
    approve: bool
    reason: str = ""


class Submit(BaseModel):
    verify_job_id: str
    submitted_by: Actor


def _inbox_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except InboxError as err:
        raise HTTPException(err.status, str(err)) from None


@router.get("/runs/{run_id}/verdicts")
def verdict_feed(request: Request, run_id: str, start: int | None = None, follow: bool = True):
    """SSE: every gate verdict (`verdict`) and every runtime alert (`alert`), live."""
    return deps.sse(request, deps.get_run(request, run_id).verdicts, start, follow)


@router.get("/approvals")
def approvals(request: Request) -> dict[str, Any]:
    """The inbox: payment approvals waiting in any run, and policy patches."""
    reg = deps.registry(request)
    payments = []
    for handle in reg.runs.values():
        with handle.lock:
            for r in handle.state.approval_requests.values():
                if r.status == "pending":
                    payments.append(
                        {
                            "run_id": handle.id,
                            "id": r.id,
                            "invoice": r.subject,
                            "amount": r.instruction.amount,
                            "payee_account": r.instruction.payee_account,
                            "requested_by": r.requested_by,
                        }
                    )
    patches = [
        r.model_dump(mode="json", exclude={"policy"}) | {"version": r.policy.version}
        for r in reg.inbox.requests.values()
    ]
    return {"payments": payments, "patches": patches}


@router.post("/runs/{run_id}/approvals/{request_id}/decide")
def decide_payment(
    request: Request, run_id: str, request_id: str, body: Decision
) -> dict[str, Any]:
    """Decide a payment approval through Tools, so Blue's gate (and its segregation-of-duties
    checks) rules on who may decide."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        result = handle.sandbox.tools.call(
            body.actor,
            "approvals.decide",
            DecideArgs(request=request_id, approve=body.approve, reason=body.reason),
        )
    return {
        "ok": result.ok,
        "decision": result.verdict.decision,
        "fired": result.verdict.fired,
        "error": result.data.get("error"),
    }


@router.post("/approvals")
def submit_patch(request: Request, body: Submit) -> dict[str, Any]:
    """Put a verified policy in the inbox, with its evidence pack."""
    job = deps.get_job(request, body.verify_job_id)
    if job.kind != "verify" or job.status != "done":
        raise HTTPException(409, f"{body.verify_job_id} isn't a finished verification")
    policy = Policy.model_validate(job.meta["policy_json"])
    pack = job.result
    req = _inbox_call(
        deps.registry(request).inbox.submit,
        policy,
        body.submitted_by,
        approvable=bool(pack["approvable"]),
        evidence=pack["version"],
        checks=[{"name": c["name"], "passed": c["passed"]} for c in pack["checks"]],
    )
    return req.model_dump(mode="json")


@router.post("/approvals/{patch_id}/decide")
def decide_patch(request: Request, patch_id: str, body: Decision) -> dict[str, Any]:
    reg = deps.registry(request)
    return _inbox_call(
        reg.inbox.decide, patch_id, body.actor, body.approve, body.reason
    ).model_dump(mode="json")


@router.post("/policies/{version}/apply")
def apply_policy(request: Request, version: str) -> dict[str, Any]:
    """Applies only a patch a second person approved in the inbox; new runs can then use it."""
    reg = deps.registry(request)
    req = _inbox_call(reg.inbox.apply, version)
    reg.applied[version] = req.policy
    if reg.store is not None:
        reg.store.save_policy(
            req.policy,
            approval={"patch": req.id, "by": req.decided_by, "submitted_by": req.submitted_by},
        )
    return {"applied": version, "patch": req.id, "approved_by": req.decided_by}


@router.get("/explain/{entity_type}/{entity_id}")
def explain_route(
    request: Request, entity_type: str, entity_id: str, run: str, question: str | None = None
) -> dict[str, Any]:
    """A cited answer to "why?" about a payment, invoice, or change request in a run."""
    handle = deps.get_run(request, run)
    with handle.lock:
        out = explain_safely(handle.state, entity_type, entity_id, question)
    if "error" in out:
        raise HTTPException(404 if out["error"].startswith("no ") else 400, out["error"])
    return out
