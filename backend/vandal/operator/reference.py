"""R2: the deterministic, no-LLM reference Operator, plus the simulated approver.

Search and verification always use this Operator (IMPLEMENTATION 0). It acts only through
Tools.call and reads only Tools.view; it never sees oracle labels.
"""

from __future__ import annotations

from typing import Literal

from vandal.contracts.entities import Actor, Case, Payment
from vandal.contracts.events import ChannelEvent
from vandal.contracts.interfaces import Tools
from vandal.twin import money_in
from vandal.twin.facts import match_facts, prior_settled_payments
from vandal.twin.flows import (
    AccountRef,
    CallbackArgs,
    CaseClose,
    CaseOpen,
    CashArgs,
    ChangeRef,
    ChangeRequestArgs,
    DecideArgs,
    InboundEvidenceArgs,
    InvoiceArgs,
    InvoiceRef,
    PaymentRef,
    Reassign,
    RecoveryRef,
    RefundArgs,
    RepaymentArgs,
    RequestRef,
    ScheduleArgs,
    TransactionRef,
)
from vandal.twin.profile import Profile

RetryPolicy = Literal["no_key", "query_first"]


class ReferenceOperator:
    """`retry` is what the Operator does when a submission's ack never comes. v0 resends it
    with no idempotency key (DESIGN 11, Scenario B). Whatever the policy, it follows a T3 hold:
    asks the bank first, or resends with a key."""

    REMIND_AFTER = 2  # business days an approval may wait before a reminder (O3)
    ESCALATE_AFTER = 4  # ... before it goes to the next approver

    def __init__(self, profile: Profile, retry: RetryPolicy = "no_key") -> None:
        self.actor = Actor(id=profile.operator.id, role="operator")
        self.horizon = profile.operator.payment_horizon_days
        self.retry = retry
        self.approvers = profile.approval_matrix.approvers

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None:
        match ev.subject:
            case "daily_ops":
                self._intake(tools)
                self._chase_approvals(tools)
                self._schedule(tools)
            case "payment_batch":
                self._schedule(tools)
                self._pay(tools)
            case "bank_feed":
                self._reconcile(tools)
                self._apply_cash(tools)
                self._retry_timeouts(tools)
                self._work_cases(tools)  # the bank may have answered a recall today
            case "retry_timer":
                self._retry_timeouts(tools)
            case _ if ev.meta.get("intent") in ("vendor_bank_change", "vendor_contact_change"):
                self._change_request(ev, tools)
            case _ if ev.meta.get("intent") == "invoice":
                self._receive_invoice(ev, tools)
            case _ if ev.meta.get("intent") == "change_confirmation":
                self._inbound_confirmation(ev, tools)
            case _ if ev.meta.get("intent") == "callback_answered":
                self._apply(str(ev.meta["request"]), tools)
            case _ if ev.meta.get("intent") == "refund_request":
                self._refund(ev, tools)
            case _ if ev.meta.get("intent") == "guard_alert":
                self._on_alert(ev, tools)
            case _ if ev.meta.get("intent") == "payment_inquiry":
                self._on_inquiry(ev, tools)

    # --- exceptions and recovery (O2) -------------------------------------------------------

    RECOVERABLE = ("INV-2", "INV-5")  # the money went somewhere the approval didn't say

    def _on_alert(self, ev: ChannelEvent, tools: Tools) -> None:
        """Blue saw an executed payment break the authorization chain: open a recovery case."""
        if ev.meta.get("invariant") not in self.RECOVERABLE:
            return
        payment = str(ev.meta["subject"])
        if payment in tools.view.payments:
            self._open_recovery(payment, f"{ev.meta['invariant']}: {ev.meta['message']}", tools)

    def _on_inquiry(self, ev: ChannelEvent, tools: Tools) -> None:
        """A vendor says it wasn't paid. If a payment made in this run went to an account that
        was never verified through an authenticated channel, it was misdirected. (An account
        superseded since was verified when it was paid.)"""
        state = tools.view
        vendor = str(ev.meta.get("vendor", ""))
        for pay in list(state.payments.values()):
            instr = state.payment_instructions[pay.instruction]
            if state.invoices[instr.invoice].vendor != vendor or pay.submitted_on is None:
                continue
            if pay.status not in ("submitted", "acknowledged", "settled"):
                continue
            if pay.submitted_on < 0:
                continue  # seeded history, paid before the books opened
            payee = state.vendor_bank_accounts.get(instr.payee_account)
            never_verified = (
                payee is None
                or payee.status in ("unverified", "rejected")
                or (payee.verified_by not in ("phone_outbound", "portal"))
            )
            if never_verified:
                self._open_recovery(
                    pay.id,
                    f"{vendor} reports non-payment; {pay.id} went to "
                    f"{instr.payee_account}, not a verified account",
                    tools,
                )

    def _open_recovery(self, payment: str, reason: str, tools: Tools) -> None:
        if any(c.subject == payment for c in tools.view.cases.values()):
            return
        tools.call(
            self.actor, "cases.open", CaseOpen(subject=payment, kind="recovery", reason=reason)
        )
        case = next(c for c in tools.view.cases.values() if c.subject == payment)
        self.on_case(case, tools)

    def _work_cases(self, tools: Tools) -> None:
        for case in [c for c in tools.view.cases.values() if c.status == "open"]:
            self.on_case(case, tools)

    def on_case(self, case: Case, tools: Tools) -> None:
        """Work a recovery case one step further each time it comes up. Every step is a tool
        call through Blue; re-paying the vendor waits for a human in the approvals inbox."""
        if case.kind != "recovery" or case.status != "open":
            return
        state = tools.view
        pay = state.payments.get(case.subject)
        if pay is None:
            return
        ref = RecoveryRef(payment=pay.id, case=case.id)
        instr = state.payment_instructions[pay.instruction]
        if pay.status in ("submitted", "acknowledged", "settled"):
            tools.call(self.actor, "payments.mark_misdirected", ref)
        pay = tools.view.payments[pay.id]
        if pay.status == "misdirected" and pay.recall == "none":
            tools.call(self.actor, "payments.recall", ref)
        if pay.recall == "succeeded" and f"booked the recall of {pay.id}" not in case.actions:
            tools.call(self.actor, "payments.book_recall", ref)
        payee = tools.view.vendor_bank_accounts.get(instr.payee_account)
        if (
            payee is not None
            and payee.status != "rejected"
            and (
                payee.status != "verified"
                or payee.source.startswith("change_request:")
                and payee.verified_by not in ("phone_outbound", "portal")
            )
        ):
            tools.call(
                self.actor, "vendors.reject_account", AccountRef(account=payee.id, case=case.id)
            )
        state = tools.view
        invoice = instr.invoice
        repaid = [
            p
            for p in state.payments.values()
            if p.id != pay.id
            and p.status in ("submitted", "acknowledged", "settled")
            and state.payment_instructions[p.instruction].invoice == invoice
        ]
        # One request per case: a denied repayment is never resubmitted unchanged (DESIGN 6);
        # the case stays open for a person to decide what happens next.
        asked = any(
            r.subject == invoice and r.kind == "repayment" for r in state.approval_requests.values()
        )
        if not repaid and not asked and state.invoices[invoice].status in ("approved", "scheduled"):
            tools.call(
                self.actor,
                "approvals.request_repayment",
                RepaymentArgs(invoice=invoice, case=case.id),
            )
        pay = tools.view.payments[pay.id]
        if repaid and pay.recall in ("failed", "succeeded"):
            outcome = (
                "recalled; vendor re-paid"
                if pay.recall == "succeeded"
                else f"vendor re-paid by {repaid[0].id}; {pay.id} is a receivable to pursue"
            )
            tools.call(self.actor, "cases.resolve", CaseClose(case=case.id, outcome=outcome))

    # --- working with approvers (O3) --------------------------------------------------------

    def _chase_approvals(self, tools: Tools) -> None:
        """Remind a slow approver after REMIND_AFTER business days; after ESCALATE_AFTER, send
        the request to the next approver up."""
        day = tools.view.day
        for req in list(tools.view.approval_requests.values()):
            if req.status != "pending":
                continue
            age = day - req.requested_on
            if age >= self.ESCALATE_AFTER and req.assigned_to is None:
                current = self._approver_for(req.instruction.amount)
                above = [
                    a
                    for a in self.approvers
                    if a.id != current.id
                    and (
                        a.max_amount is None
                        or (current.max_amount is not None and a.max_amount > current.max_amount)
                    )
                ]
                if above:
                    tools.call(
                        self.actor, "approvals.reassign", Reassign(request=req.id, to=above[0].id)
                    )
            elif age >= self.REMIND_AFTER and req.reminders == 0:
                tools.call(self.actor, "approvals.remind", RequestRef(request=req.id))

    def _approver_for(self, amount: int):
        return next(a for a in self.approvers if a.max_amount is None or amount <= a.max_amount)

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
                self._send(tools, "payments.submit", pay)

    def _send(self, tools: Tools, tool: str, pay: Payment) -> None:
        """Submit or retry. If a control holds it for want of an idempotency key, resend with
        one: the instruction id, the same on every attempt."""
        result = tools.call(self.actor, tool, PaymentRef(payment=pay.id))
        if _held_by(result, ".key"):
            key = PaymentRef(payment=pay.id, idempotency_key=pay.instruction)
            tools.call(self.actor, tool, key)

    def _retry_timeouts(self, tools: Tools) -> None:
        """A payment still waiting on its ack at the bank feed timed out."""
        for pay in list(tools.view.payments.values()):
            if pay.status != "submitted" or pay.bank_status == "processed":
                continue
            if self.retry == "query_first":
                tools.call(self.actor, "payments.query_status", PaymentRef(payment=pay.id))
                if tools.view.payments[pay.id].bank_status == "processed":
                    continue
            result = tools.call(self.actor, "payments.retry", PaymentRef(payment=pay.id))
            if _held_by(result, ".query_first"):
                tools.call(self.actor, "payments.query_status", PaymentRef(payment=pay.id))
                if tools.view.payments[pay.id].bank_status != "processed":
                    tools.call(self.actor, "payments.retry", PaymentRef(payment=pay.id))
            elif _held_by(result, ".key"):
                key = PaymentRef(payment=pay.id, idempotency_key=pay.instruction)
                tools.call(self.actor, "payments.retry", key)

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

    def _apply_cash(self, tools: Tools) -> None:
        """Cash application: match each new deposit to the customer and invoices its memo
        names; reverse the application of a deposit that came back."""
        for txn in list(tools.view.bank_transactions.values()):
            if txn.reconciled or txn.amount == 0:
                continue
            if txn.returns is not None:
                tools.call(self.actor, "cash.reverse", TransactionRef(transaction=txn.id))
            elif txn.amount > 0 and txn.payment is None:
                customer, invoices = money_in.identify(tools.view, txn.memo)
                args = CashArgs(transaction=txn.id, customer=customer, invoices=invoices)
                tools.call(self.actor, "cash.apply", args)

    def _refund(self, ev: ChannelEvent, tools: Tools) -> None:
        """A customer asks for its credit back. v0 sends it where the request says, for up
        to the credit on the books; the gate decides whether that's allowed."""
        m = ev.meta
        customer = str(m["customer"])
        if customer not in tools.view.customers:
            return
        credit = money_in.credit_balance(tools.view, customer)
        amount = min(int(m["amount"]), credit)
        if amount <= 0:
            return
        tools.call(
            self.actor,
            "refunds.issue",
            RefundArgs(
                customer=customer,
                amount=amount,
                destination_account=f"{m['routing']}:{m['account']}",
                reason="overpayment refund requested",
                message=ev.id,
            ),
        )

    def _reconcile(self, tools: Tools) -> None:
        for txn in list(tools.view.bank_transactions.values()):
            if not txn.reconciled and txn.payment is not None:
                tools.call(self.actor, "ledger.reconcile", TransactionRef(transaction=txn.id))


def _held_by(result, suffix: str) -> bool:
    """Did a control with this check (e.g. T3's `.key`) hold the call?"""
    return result.verdict.decision == "hold" and any(
        c.endswith(suffix) for c in result.verdict.fired
    )


def _pending_request(tools: Tools, invoice: str) -> bool:
    return any(
        r.subject == invoice and r.status == "pending"
        for r in tools.view.approval_requests.values()
    )


class SimulatedApprover:
    """Stands in for human approvers. Each answers after its `response_days` (O3), the request
    goes to whoever it's assigned to (or the first approver whose limit covers it), and the
    approver approves when the PO matches and the vendor has enough prior payments; otherwise it
    denies with a reason. A repayment is approved only if it now goes to a verified account."""

    def __init__(self, profile: Profile) -> None:
        matrix = profile.approval_matrix
        self.approvers = matrix.approvers
        self.min_prior = matrix.min_prior_payments
        self.tolerance_bps = matrix.match_tolerance_pct * 100

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None:
        if ev.subject != "approvals_inbox":
            return
        day = tools.view.day
        for req in list(tools.view.approval_requests.values()):
            if req.status != "pending":
                continue
            amount = req.instruction.amount
            approver = next(
                (a for a in self.approvers if a.id == req.assigned_to),
                next(a for a in self.approvers if a.max_amount is None or amount <= a.max_amount),
            )
            if day - req.requested_on < approver.response_days:
                continue  # still sitting in their inbox
            approve, reason = self._decide(tools, req.subject)
            if approve and req.kind == "repayment":
                payee = tools.view.vendor_bank_accounts.get(req.instruction.payee_account)
                if payee is None or payee.status != "verified":
                    approve, reason = False, f"{req.instruction.payee_account} isn't verified"
            tools.call(
                Actor(id=approver.id, role="approver"),
                "approvals.decide",
                DecideArgs(request=req.id, approve=approve, reason=reason),
            )

    def _work_cases(self, tools: Tools) -> None:
        for case in [c for c in tools.view.cases.values() if c.status == "open"]:
            self.on_case(case, tools)

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
