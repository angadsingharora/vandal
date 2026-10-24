"""R5: authorization-coverage analysis (DESIGN 9.1) and the first uncovered link.

Every payment should sit on an unbroken chain of authorizations:

  obligation -> approval -> execution -> settlement -> books

Each link is *covered* when an authorization binds it to the link before it: a validated, unique
obligation; an approval of the right kind for the amount; an execution that is exactly what was
approved, to an account verified through an authenticated channel, executed once; a settlement
the bank confirmed; books that recorded and reconciled it. The root cause of a violation is the
first link that isn't covered.

This is deterministic code over the twin's own records. It never reads oracle labels, so a
diagnosis is something the company could compute about itself. The trace builder
(`build_chain`) is shared with Blue's cited explanations (B5).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents
from vandal.contracts.events import Event
from vandal.twin.facts import normalize_number
from vandal.twin.state import State
from vandal.verify.invariants import AUTHENTICATED_CHANNELS, EXECUTED, Limits, Violation

GapType = Literal[
    "approval_binding",
    "verification_channel",
    "execution_idempotency",
    "duplicate_obligation",
    "aggregate_threshold",
    "refund_destination",
]
LinkName = Literal["obligation", "approval", "execution", "settlement", "books"]
LINKS: tuple[LinkName, ...] = ("obligation", "approval", "execution", "settlement", "books")


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: LinkName
    status: Literal["covered", "uncovered", "pending"]
    gap: GapType | None = None
    reason: str = ""
    entities: list[str] = []  # business keys this link rests on
    events: list[str] = []  # the events that show it
    facts: dict[str, Any] = {}


class Chain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment: str
    invoice: str
    links: list[Link]

    @property
    def first_uncovered(self) -> Link | None:
        return next((ln for ln in self.links if ln.status == "uncovered"), None)


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap: GapType
    link: LinkName
    payment: str
    reason: str
    cites: list[str]  # entity and event ids: the approval, the change, the payment, ...
    violated: list[str]  # the invariants the counterexample broke
    exposure: Cents
    also: list[GapType] = []  # later uncovered links on the same chain
    chain: Chain


# --- event index ----------------------------------------------------------------------------


class EventIndex:
    """Which events mention which business keys. Built once per state."""

    def __init__(self, events: Iterable[Event]) -> None:
        self.by_id: dict[str, Event] = {}
        self.mentions: dict[str, list[str]] = {}
        for ev in events:
            self.by_id[ev.id] = ev
            for key in sorted(_ids_in(ev.payload)):
                self.mentions.setdefault(key, []).append(ev.id)

    def find(self, key: str, *kinds: str) -> list[str]:
        """Events mentioning `key`, optionally of the given kinds, in log order."""
        return [e for e in self.mentions.get(key, []) if not kinds or self.by_id[e].kind in kinds]

    def with_verdicts(self, event_ids: list[str]) -> list[str]:
        """The events plus the gate verdicts that allowed them, in log order."""
        out = set(event_ids)
        for e in event_ids:
            out |= {c for c in self.by_id[e].caused_by if self.by_id[c].kind == "gate.verdict"}
        return sorted(out, key=lambda e: self.by_id[e].seq)


_PREFIXES = ("INV-", "APR-", "AQ-", "PI-", "PAY-", "BT-", "BA-", "CR-", "MSG-", "JE-", "V-")


def _ids_in(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value.startswith(_PREFIXES) else set()
    if isinstance(value, dict):
        return set().union(*(_ids_in(v) for v in value.values())) if value else set()
    if isinstance(value, list | tuple):
        return set().union(*(_ids_in(v) for v in value)) if value else set()
    return set()


# --- the chain ------------------------------------------------------------------------------


def build_chain(
    state: State, payment: str, limits: Limits | None = None, index: EventIndex | None = None
) -> Chain:
    limits = limits or Limits()
    index = index or EventIndex(state.events)
    pay = state.payments[payment]
    instr = state.payment_instructions[pay.instruction]
    inv = state.invoices[instr.invoice]
    approvals = [a for a in state.approvals.values() if a.subject == inv.id]
    approval = approvals[-1] if approvals else None
    links = [
        _obligation(state, index, inv, pay),
        _approval(state, index, inv, approval, limits),
        _execution(state, index, inv, pay, instr, approval),
        _settlement(state, index, pay),
        _books(state, index, inv, pay),
    ]
    return Chain(payment=pay.id, invoice=inv.id, links=links)


def _paid_invoices(state: State) -> dict[str, list[str]]:
    paid: dict[str, list[str]] = {}
    for p in state.payments.values():
        if p.status in EXECUTED:
            paid.setdefault(state.payment_instructions[p.instruction].invoice, []).append(p.id)
    return paid


def _obligation(state: State, index: EventIndex, inv, pay) -> Link:
    events = index.with_verdicts(index.find(inv.id, "invoice.received", "invoice.validated"))
    entities = [inv.id] + ([inv.po] if inv.po else [])
    paid = _paid_invoices(state)
    twins = [
        o.id
        for o in state.invoices.values()
        if o.id != inv.id
        and o.vendor == inv.vendor
        and o.id in paid
        and (
            normalize_number(o.number) == normalize_number(inv.number)
            or (o.amount == inv.amount and abs(o.received_on - inv.received_on) <= 30)
        )
    ]
    if twins:
        return Link(
            name="obligation",
            status="uncovered",
            gap="duplicate_obligation",
            reason=f"{inv.id} looks like already-paid {', '.join(twins)} "
            "(same vendor; same normalized number, or same amount within 30 "
            "days)",
            entities=entities + twins,
            events=events,
            facts={"duplicates": twins},
        )
    return Link(
        name="obligation",
        status="covered",
        entities=entities,
        events=events,
        reason="validated (3-way match) and unique",
    )


def _approval(state: State, index: EventIndex, inv, approval, limits: Limits) -> Link:
    if approval is None:
        return Link(
            name="approval",
            status="uncovered",
            gap="approval_binding",
            reason=f"nothing approved {inv.id}",
            entities=[inv.id],
        )
    events = index.with_verdicts(
        index.find(approval.id, "approval.granted") + index.find(inv.id, "approval.requested")
    )
    entities = [approval.id]
    facts = {
        "via": approval.via,
        "approver": approval.approver,
        "approved_amount": approval.approved_instruction.amount,
    }
    if approval.via != "approvals_inbox":
        # Same vendor, inside the window, approved by policy only: do they add up past the
        # threshold? Splitting an invoice must not get around the inbox (INV-6).
        siblings = [
            a
            for a in state.approvals.values()
            if a.via == "policy"
            and state.invoices[a.subject].vendor == inv.vendor
            and abs(state.invoices[a.subject].received_on - inv.received_on) < limits.window_days
        ]
        total = sum(a.approved_instruction.amount for a in siblings)
        facts["vendor_window_total"] = total
        if total > limits.threshold:
            return Link(
                name="approval",
                status="uncovered",
                gap="aggregate_threshold",
                reason=f"{inv.vendor} approvals by policy total {total}, over "
                f"{limits.threshold}, with no inbox approval",
                entities=entities + [a.id for a in siblings],
                events=events,
                facts=facts,
            )
    return Link(
        name="approval",
        status="covered",
        entities=entities,
        events=events,
        facts=facts,
        reason=f"approved via {approval.via} by {approval.approver}",
    )


def _execution(state: State, index: EventIndex, inv, pay, instr, approval) -> Link:
    """Executed exactly as approved, to an account verified through an authenticated channel,
    and only once. Every gap found is kept; the first is the link's gap."""
    events = index.with_verdicts(
        index.find(pay.id, "instruction.built", "payment.submitted", "bank.ack")
    )
    entities = [pay.id, instr.id, instr.payee_account]
    facts: dict[str, Any] = {"executed_payee": instr.payee_account, "executed_amount": instr.amount}
    acct = state.vendor_bank_accounts.get(instr.payee_account)
    provenance = _account_provenance(state, index, instr.payee_account)
    gaps: list[tuple[GapType, str, list[str]]] = []

    if approval is not None:
        ai = approval.approved_instruction
        facts |= {"approved_payee": ai.payee_account, "approved_amount": ai.amount}
        drift = [
            name
            for name, got, want in (
                ("payee_account", instr.payee_account, ai.payee_account),
                ("amount", instr.amount, ai.amount),
            )
            if got != want
        ]
        if drift:
            gaps.append(
                (
                    "approval_binding",
                    f"{pay.id} executed {' and '.join(drift)} different from what "
                    f"{approval.id} approved: the approval doesn't bind the instruction",
                    [approval.id] + provenance["entities"],
                )
            )

    verified = (
        acct is not None
        and acct.status not in ("unverified", "rejected")
        and acct.verified_by in AUTHENTICATED_CHANNELS
        and acct.verified_on is not None
        and acct.verified_on <= (pay.submitted_on or 0)
    )
    if not verified:
        facts |= {
            "payee_status": acct.status if acct else None,
            "verified_by": acct.verified_by if acct else None,
        }
        gaps.append(
            (
                "verification_channel",
                f"{instr.payee_account} was never verified through an authenticated "
                f"channel before {pay.id} executed",
                provenance["entities"],
            )
        )
    elif fresh := _fresh_callback_contacts(state, instr.payee_account):
        # Verified by an outbound call, but to a contact that was itself changed shortly before
        # the request: the callback proved only that whoever controls that number said yes.
        gaps.append(
            (
                "verification_channel",
                f"{instr.payee_account} was verified by calling "
                f"{', '.join(c for c, _ in fresh)}, a contact changed on day "
                f"{fresh[0][1]}, inside the request's window",
                provenance["entities"] + [c for c, _ in fresh],
            )
        )

    siblings = _paid_invoices(state).get(inv.id, [])
    if len(siblings) > 1:
        gaps.append(
            (
                "execution_idempotency",
                f"{inv.id} executed {len(siblings)} times ({', '.join(siblings)})",
                siblings,
            )
        )

    if not gaps:
        return Link(
            name="execution",
            status="covered",
            entities=entities,
            events=events,
            facts=facts,
            reason="executed as approved, once, to a verified account",
        )
    gap, reason, cited = gaps[0]
    facts["other_gaps"] = [g for g, _, _ in gaps[1:]]
    if gap in ("approval_binding", "verification_channel"):
        extra = set(provenance["events"])
        if gap == "approval_binding" and approval is not None:
            extra |= set(index.with_verdicts(index.find(approval.id, "approval.granted")))
        events = sorted(set(events) | extra, key=lambda e: index.by_id[e].seq)
    return Link(
        name="execution",
        status="uncovered",
        gap=gap,
        reason=reason,
        entities=entities + cited,
        events=events,
        facts=facts,
    )


def _fresh_callback_contacts(state: State, account: str, window: int = 30) -> list[tuple[str, int]]:
    """Contacts dialed in the callbacks that verified `account`, if they were added within
    `window` days before the change request: (contact, valid_from)."""
    acct = state.vendor_bank_accounts.get(account)
    if acct is None or not acct.source.startswith("change_request:"):
        return []
    cr = state.change_requests.get(acct.source.split(":", 1)[1])
    if cr is None:
        return []
    out = []
    for ev_id in cr.evidence:
        ev = state.evidence[ev_id]
        if ev.channel != "phone_outbound" or not ev.confirms or ev.contact is None:
            continue
        contact = state.vendor_contacts.get(ev.contact)
        if contact and contact.valid_from > cr.received_on - window:
            out.append((contact.id, contact.valid_from))
    return out


def _account_provenance(state: State, index: EventIndex, account: str) -> dict[str, list[str]]:
    """How an account got into the vendor master: the change request, its message, its gate
    verdict."""
    changed = index.find(account, "vendor.bank_changed")
    entities: list[str] = []
    events: list[str] = list(changed)
    for e in changed:
        cr = index.by_id[e].payload["request"]
        entities.append(cr)
        created = index.find(cr, "change_request.created")
        events += index.with_verdicts(created)
        msg = state.change_requests[cr].message if cr in state.change_requests else None
        if msg:
            entities.append(msg)
            events += index.find(msg, "channel.received")
    return {"entities": entities, "events": events}


def _settlement(state: State, index: EventIndex, pay) -> Link:
    events = index.find(pay.id, "bank.settled")
    txns = [t.id for t in state.bank_transactions.values() if t.payment == pay.id]
    if pay.status != "settled":
        return Link(
            name="settlement",
            status="pending",
            entities=[pay.id],
            events=events,
            reason=f"{pay.id} is {pay.status}",
        )
    return Link(
        name="settlement",
        status="covered",
        entities=txns,
        events=events,
        reason=f"bank confirmed {', '.join(txns) or pay.id}",
    )


def _books(state: State, index: EventIndex, inv, pay) -> Link:
    entries = [
        je.id for je in state.journal if je.memo in (f"Approve {inv.id}", f"Submit {pay.id}")
    ]
    txns = [t for t in state.bank_transactions.values() if t.payment == pay.id]
    events = index.find(pay.id, "bank.reconciled") + [
        e for je in entries for e in index.find(je, "journal.posted")
    ]
    if (pay.submitted_on or 0) < 0:
        return Link(
            name="books",
            status="covered",
            entities=[pay.id],
            events=events,
            reason="pre-opening history",
        )
    if len(entries) < 2:
        return Link(
            name="books",
            status="pending",
            entities=entries,
            events=events,
            reason="approval and payment entries not both posted yet",
        )
    if txns and not all(t.reconciled for t in txns):
        return Link(
            name="books",
            status="pending",
            entities=entries,
            events=events,
            reason="bank line not reconciled yet",
        )
    return Link(
        name="books",
        status="covered",
        entities=entries,
        events=events,
        reason="posted and reconciled",
    )


# --- diagnosis ------------------------------------------------------------------------------

EXPOSURE_INVARIANTS = ("INV-2", "INV-3", "INV-4", "INV-5", "INV-6")


def diagnose(
    state: State, violations: list[Violation], limits: Limits | None = None
) -> Diagnosis | None:
    """Root cause of a counterexample: the first uncovered link on the chain of the payment
    with the most exposure. None if every violating payment's chain is covered."""
    index = EventIndex(state.events)
    exposure: dict[str, Cents] = {}
    violated: dict[str, set[str]] = {}
    for v in violations:
        if v.invariant in EXPOSURE_INVARIANTS and v.subject in state.payments:
            exposure[v.subject] = max(exposure.get(v.subject, 0), v.exposure)
            violated.setdefault(v.subject, set()).add(v.invariant)
    for payment in sorted(exposure, key=lambda p: (-exposure[p], p)):
        chain = build_chain(state, payment, limits, index)
        first = chain.first_uncovered
        if first is None:
            continue
        later: list[GapType] = list(first.facts.get("other_gaps", [])) + [
            ln.gap
            for ln in chain.links[chain.links.index(first) + 1 :]
            if ln.status == "uncovered" and ln.gap
        ]
        return Diagnosis(
            gap=first.gap,
            link=first.name,
            payment=payment,
            reason=first.reason,
            cites=sorted(set(first.entities)) + first.events,
            violated=sorted(violated[payment]),
            exposure=exposure[payment],
            also=later,
            chain=chain,
        )
    return None
