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
    CallbackArgs,
    ChangeRef,
    ChangeRequestArgs,
    DecideArgs,
    InboundEvidenceArgs,
    InvoiceArgs,
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
            case _ if ev.meta.get("intent") in ("vendor_bank_change", "vendor_contact_change"):
                self._change_request(ev, tools)
            case _ if ev.meta.get("intent") == "invoice":
                self._receive_invoice(ev, tools)
            case _ if ev.meta.get("intent") == "change_confirmation":
                self._inbound_confirmation(ev, tools)
            case _ if ev.meta.get("intent") == "callback_answered":
                self._apply(str(ev.meta["request"]), tools)

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

    def _change_request(self, ev: ChannelEvent, tools: Tools) -> None:
        """Intake of a vendor-master change. The reference Operator reads the structured fields
        the message carries; the LLM Operator (O1) extracts them from the body instead."""
        m = ev.meta
        bank = m["intent"] == "vendor_bank_change"
        result = tools.call(
            self.actor,
            "vendors.change_request",
            ChangeRequestArgs(
                vendor=str(m["vendor"]),
                fields="bank" if bank else "contact",
                channel=ev.channel,
                sender=ev.sender,
                message=ev.id,
                routing=str(m["routing"]) if bank else None,
                account=str(m["account"]) if bank else None,
                contact_name=None if bank else str(m.get("contact_name", "")),
                contact_email=None if bank else str(m.get("contact_email", "")),
                contact_phone=None if bank else str(m.get("contact_phone", "")),
            ),
        )
        held = [
            c
            for c in tools.view.change_requests.values()
            if c.message == ev.id and c.status == "held"
        ]
        if held:
            self._verify(held[-1].id, result.verdict.facts.get("gate.requires", []), tools)

    def _receive_invoice(self, ev: ChannelEvent, tools: Tools) -> None:
        m = ev.meta
        tools.call(
            self.actor,
            "invoices.receive",
            InvoiceArgs(
                vendor=str(m["vendor"]),
                number=str(m["number"]),
                amount=int(m["amount"]),
                dimension=str(m.get("dimension", "P-01")),
                due_in_days=int(m.get("due_in_days", 5)),
                kind=m.get("kind", "invoice"),
                supersedes=m.get("supersedes") or None,
                po=m.get("po") or None,
                message=ev.id,
            ),
        )

    def _verify(self, change: str, requires: list[dict], tools: Tools) -> None:
        """Answer an evidence-gated hold the way the control asks. A portal submission carries
        its own evidence; otherwise an outbound callback to the contact on file as of
        `contact_as_of`. Inbound calls are never solicited."""
        cr = tools.view.change_requests[change]
        portal = cr.channel == "portal" and any(
            "portal" in r.get("accepted_channels", []) for r in requires
        )
        if portal and tools.call(self.actor, "evidence.record_portal", ChangeRef(change=change)).ok:
            self._apply(change, tools)
            return
        for req in requires:
            if "phone_outbound" in req.get("accepted_channels", []):
                tools.call(
                    self.actor,
                    "evidence.request_callback",
                    CallbackArgs(
                        change=change,
                        contact_as_of=req.get("contact_as_of") or "before_request",
                        window_days=req.get("window_days"),
                    ),
                )
                return

    def _inbound_confirmation(self, ev: ChannelEvent, tools: Tools) -> None:
        """Someone calls in to confirm a pending change: record it as evidence, then let the
        gate decide whether that evidence is enough."""
        vendor = str(ev.meta["vendor"])
        result = tools.call(
            self.actor,
            "evidence.record_inbound",
            InboundEvidenceArgs(
                vendor=vendor,
                channel=ev.channel,
                message=ev.id,
                voice_match=ev.meta.get("voice_match"),
            ),
        )
        if result.ok:
            held = [
                c
                for c in tools.view.change_requests.values()
                if c.vendor == vendor and c.status == "held"
            ]
            self._apply(held[-1].id, tools)

    def _apply(self, change: str, tools: Tools) -> None:
        cr = tools.view.change_requests.get(change)
        if cr is not None and cr.status == "held":
            tools.call(self.actor, "vendors.apply_change", ChangeRef(change=change))

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
