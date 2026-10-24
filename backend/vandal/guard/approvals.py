"""B3: the approvals inbox for policy patches (DESIGN 6.1, 10).

Payment approvals live in the twin (ApprovalRequest, decided through `approvals.decide` and
Blue's gate). Policy patches live here, outside the twin, because a patch changes the gate
itself. The rules are the same:

  - the synthesizer or a person may *submit* a patch, with its evidence pack
  - only an approver (a human) may *decide* it, and never the one who submitted it; in
    single-user mode that means a second person approves
  - a patch whose evidence pack isn't approvable can't be approved
  - a patch is *applied* only after it's approved, and only once

The Operator has no part in any of it.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Actor
from vandal.synth.templates import Policy


class InboxError(Exception):
    """A request the inbox's rules refuse. `status` is the HTTP status the API should return."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    policy: Policy
    submitted_by: str
    submitter_role: str
    evidence: str | None = None  # evidence pack id
    approvable: bool
    checks: list[dict[str, Any]] = []
    status: Literal["pending", "approved", "denied", "applied"] = "pending"
    decided_by: str | None = None
    reason: str = ""


SUBMITTERS = ("synthesizer", "approver")


class PolicyInbox:
    def __init__(self) -> None:
        self.requests: dict[str, PatchRequest] = {}

    def submit(
        self,
        policy: Policy,
        by: Actor,
        *,
        approvable: bool,
        evidence: str | None = None,
        checks: list[dict[str, Any]] | None = None,
    ) -> PatchRequest:
        if by.role not in SUBMITTERS:
            raise InboxError(f"{by.id} ({by.role}) can't submit policy patches", 403)
        req = PatchRequest(
            id=f"PATCH-{uuid.uuid4().hex[:8]}",
            policy=policy,
            submitted_by=by.id,
            submitter_role=by.role,
            evidence=evidence,
            approvable=approvable,
            checks=checks or [],
        )
        self.requests[req.id] = req
        return req

    def get(self, patch_id: str) -> PatchRequest:
        if patch_id not in self.requests:
            raise InboxError(f"no patch {patch_id}", 404)
        return self.requests[patch_id]

    def decide(self, patch_id: str, by: Actor, approve: bool, reason: str = "") -> PatchRequest:
        req = self.get(patch_id)
        if by.role != "approver":
            raise InboxError(
                f"{by.id} ({by.role}) can't decide policy patches; only an approver can", 403
            )
        if by.id == req.submitted_by:
            raise InboxError(
                f"{by.id} submitted {req.id} and can't approve it; a second approver must", 403
            )
        if req.status != "pending":
            raise InboxError(f"{req.id} is {req.status}")
        if approve and not req.approvable:
            raise InboxError(
                f"{req.id}'s evidence pack isn't approvable: a patch that failed "
                "verification can't be approved"
            )
        req.status = "approved" if approve else "denied"
        req.decided_by = by.id
        req.reason = reason
        return req

    def apply(self, version: str) -> PatchRequest:
        """Mark the approved patch for `version` applied; raises if nothing approved it."""
        approved = [
            r
            for r in self.requests.values()
            if r.policy.version == version and r.status == "approved"
        ]
        if not approved:
            pending = [
                r.id
                for r in self.requests.values()
                if r.policy.version == version and r.status == "pending"
            ]
            hint = f" ({', '.join(pending)} is waiting for a decision)" if pending else ""
            raise InboxError(f"{version} needs an approved patch in the inbox to apply{hint}")
        req = approved[-1]
        req.status = "applied"
        return req

    def violations(self) -> list[str]:
        """INV-10 for patches: nobody approved their own (the rules above make this empty)."""
        return [
            r.id
            for r in self.requests.values()
            if r.decided_by is not None and r.decided_by == r.submitted_by
        ]
