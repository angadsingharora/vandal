"""R2: the deterministic, no-LLM reference Operator, plus the simulated approver.

Search and verification always use this Operator (IMPLEMENTATION 0). It acts only through
Tools.call and reads only Tools.view; it never sees oracle labels.
"""

from __future__ import annotations

from vandal.contracts.entities import Actor, Case
from vandal.contracts.events import ChannelEvent
from vandal.contracts.interfaces import Tools
from vandal.twin.facts import match_facts, prior_settled_payments
from vandal.twin.flows import (
    DecideArgs,
    InvoiceRef,
    PaymentRef,
    ScheduleArgs,
    TransactionRef,
)
from vandal.twin.profile import Profile


class ReferenceOperator:
    def __init__(self, profile: Profile) -> None:
        self.actor = Actor(id=profile.operator.id, role="operator")
        self.horizon = profile.operator.payment_horizon_days

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None:
        match ev.subject:
            case "daily_ops":
                self._intake(tools)
                self._schedule(tools)
            case "payment_batch":
                self._schedule(tools)
                self._pay(tools)
            case "bank_feed":
                self._reconcile(tools)

    def on_case(self, case: Case, tools: Tools) -> None:
        """Exceptions and recovery land in O2."""

    def _intake(self, tools: Tools) -> None:
        for inv in list(tools.view.invoices.values()):
            if inv.status == "received":
                tools.call(self.actor, "invoices.validate", InvoiceRef(invoice=inv.id))
        for inv in list(tools.view.invoices.values()):
            if inv.status == "validated" and not _pending_request(tools, inv.id):
                tools.call(self.actor, "approvals.request", InvoiceRef(invoice=inv.id))

    def _schedule(self, tools: Tools) -> None:
        day = tools.view.day
        for inv in list(tools.view.invoices.values()):
            if inv.status == "approved" and inv.due_date <= day + self.horizon:
                tools.call(
                    self.actor, "payments.schedule", ScheduleArgs(invoice=inv.id, pay_on=day)
                )

    def _pay(self, tools: Tools) -> None:
        day = tools.view.day
        for inv in list(tools.view.invoices.values()):
            if inv.status == "scheduled" and (inv.scheduled_for or 0) <= day:
                tools.call(self.actor, "payments.execute", InvoiceRef(invoice=inv.id))
        for pay in list(tools.view.payments.values()):
            if pay.status == "scheduled":
                tools.call(self.actor, "payments.submit", PaymentRef(payment=pay.id))

    def _reconcile(self, tools: Tools) -> None:
        for txn in list(tools.view.bank_transactions.values()):
            if not txn.reconciled and txn.payment is not None:
                tools.call(self.actor, "ledger.reconcile", TransactionRef(transaction=txn.id))


def _pending_request(tools: Tools, invoice: str) -> bool:
    return any(
        r.subject == invoice and r.status == "pending"
        for r in tools.view.approval_requests.values()
    )


class SimulatedApprover:
    """Stands in for a human approver: approves when the PO matches and the vendor has enough
    prior payments; otherwise denies with a reason."""

    def __init__(self, profile: Profile) -> None:
        matrix = profile.approval_matrix
        self.approvers = matrix.approvers
        self.min_prior = matrix.min_prior_payments
        self.tolerance_bps = matrix.match_tolerance_pct * 100

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None:
        if ev.subject != "approvals_inbox":
            return
        for req in list(tools.view.approval_requests.values()):
            if req.status != "pending":
                continue
            amount = req.instruction.amount
            approver = next(
                a for a in self.approvers if a.max_amount is None or amount <= a.max_amount
            )
            approve, reason = self._decide(tools, req.subject)
            tools.call(
                Actor(id=approver.id, role="approver"),
                "approvals.decide",
                DecideArgs(request=req.id, approve=approve, reason=reason),
            )

    def on_case(self, case: Case, tools: Tools) -> None:
        """The approver has no cases."""

    def _decide(self, tools: Tools, invoice: str) -> tuple[bool, str]:
        inv = tools.view.invoices[invoice]
        match = match_facts(tools.view, inv)
        if match["match.status"] not in ("ok", "not_required"):
            return False, f"PO match failed: {match['match.status']}"
        if match["match.variance_bps"] > self.tolerance_bps:
            return False, "invoice differs from PO beyond tolerance"
        prior = prior_settled_payments(tools.view, inv.vendor)
        if prior < self.min_prior:
            return False, f"only {prior} prior payments to {inv.vendor}"
        return True, "PO matches and vendor is established"
