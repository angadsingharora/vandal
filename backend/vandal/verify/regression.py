"""R7: the regression suite: about 20 legitimate cases a control must not break (DESIGN 10.4).

Each case is legitimate traffic (moves with `party=vendor`, so the oracle labels nothing) and a
check of the outcome. Cases pick their vendors from the seed, so they don't hard-code ids. A case
passes when its expectations hold *and* no invariant breaks.

Holds aren't failures. A control may hold a legitimate payment for re-approval (that's friction,
the objective's mu term), but it must never send money somewhere it shouldn't, and the
legitimate obligations it doesn't hold must still be paid.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.moves import Move
from vandal.twin.state import State
from vandal.verify.invariants import EXECUTED, Limits, check
from vandal.verify.replay import SandboxFactory, replay_detailed

AUTHENTICATED = ("phone_outbound", "portal")


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    moves: Callable[[State], list[Move]]
    expect: Callable[[State, State], list[str]]  # (seed, final) -> problems
    days: int = 2
    requires: str | None = None  # a slice that must land before this case can run


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["passed", "failed", "skipped"]
    problems: list[str] = []
    violations: list[str] = []
    holds: int = 0
    blocks: int = 0


# --- picking vendors from the seed ----------------------------------------------------------


def _pending(s: State) -> list[str]:
    return sorted(i.id for i in s.invoices.values() if i.status == "received")


def _pending_vendor(s: State, nth: int, po: bool | None = None) -> str:
    vendors = sorted(
        {
            s.invoices[i].vendor
            for i in _pending(s)
            if s.invoices[i].amount <= 2_500_000
            and (po is None or s.vendors[s.invoices[i].vendor].po_required == po)
        }
    )
    return vendors[nth]


class Unmet(LookupError):
    """The seeded company has nothing a case needs (a small custom company, say): the case is
    skipped, not failed."""


def _first(candidates, what: str) -> str:
    for c in candidates:
        return c
    raise Unmet(what)


def _quiet_vendor(s: State) -> str:
    """A vendor with nothing open."""
    busy = {s.invoices[i].vendor for i in _pending(s)}
    return _first((v for v in sorted(s.vendors) if v not in busy), "a vendor with nothing open")


def _established_non_po(s: State) -> str:
    def prior(v: str) -> int:
        return sum(
            1
            for p in s.payments.values()
            if p.status == "settled"
            and s.invoices[s.payment_instructions[p.instruction].invoice].vendor == v
        )

    return _first(
        (v for v in sorted(s.vendors) if not s.vendors[v].po_required and prior(v) >= 3),
        "a non-PO vendor with three settled payments",
    )


def _next_invoice_id(s: State, offset: int = 0) -> str:
    return f"INV-{max(int(i.split('-')[1]) for i in s.invoices) + 1 + offset}"


def _open_total(s: State, vendor: str) -> int:
    return sum(
        i.amount for i in s.invoices.values() if i.vendor == vendor and i.status == "received"
    )


def change(vendor: str, at: int, fields: str = "bank", channel: str = "email") -> Move:
    return Move(
        kind="change_request",
        at=at,
        params={"vendor": vendor, "fields": fields, "channel": channel, "party": "vendor"},
    )


def invoice(vendor: str, at: int, number: str, amount: int, **extra) -> Move:
    return Move(
        kind="submit_invoice",
        at=at,
        params={"vendor": vendor, "number": number, "amount": amount, "party": "vendor", **extra},
    )


# --- expectations ---------------------------------------------------------------------------


def _payments_for(final: State, invoice_id: str):
    return [
        p
        for p in final.payments.values()
        if p.status in EXECUTED and final.payment_instructions[p.instruction].invoice == invoice_id
    ]


def _new_account(final: State, vendor: str) -> str | None:
    found = [
        a.id
        for a in final.vendor_bank_accounts.values()
        if a.vendor == vendor and a.source.startswith("change_request:")
    ]
    return found[-1] if found else None


def pending_paid(seed: State, final: State, besides: tuple[str, ...] = ()) -> list[str]:
    """Every invoice that was open in the seed got paid (except `besides`)."""
    return [
        f"{i} not paid ({final.invoices[i].status})"
        for i in _pending(seed)
        if i not in besides and not _payments_for(final, i)
    ]


def paid_to_new_verified(final: State, vendor: str, invoice_id: str | None) -> list[str]:
    """The vendor's genuine new account was verified through an authenticated channel, and the
    invoice (if given) was paid there, once."""
    acct = _new_account(final, vendor)
    if acct is None:
        return [f"{vendor}'s change was never applied"]
    a = final.vendor_bank_accounts[acct]
    problems = []
    if a.status != "verified" or a.verified_by not in AUTHENTICATED:
        problems.append(f"{acct} is {a.status} (verified_by={a.verified_by})")
    if invoice_id:
        pays = _payments_for(final, invoice_id)
        if len(pays) != 1:
            problems.append(f"{invoice_id} paid {len(pays)} times")
        elif final.payment_instructions[pays[0].instruction].payee_account != acct:
            problems.append(
                f"{invoice_id} paid to "
                f"{final.payment_instructions[pays[0].instruction].payee_account}, "
                f"not the new account {acct}"
            )
    return problems


def _vendor_invoice(seed: State, vendor: str) -> str:
    return _first(
        (i for i in _pending(seed) if seed.invoices[i].vendor == vendor),
        f"an open invoice from {vendor}",
    )


# --- the cases ------------------------------------------------------------------------------


def _bank_change_case(
    name: str,
    desc: str,
    nth: int,
    at: int,
    channel: str = "email",
    extra: Callable[[str], list[Move]] = lambda v: [],
) -> Case:
    def moves(s: State) -> list[Move]:
        v = _pending_vendor(s, nth)
        return [change(v, at, channel=channel), *extra(v)]

    def expect(seed: State, final: State) -> list[str]:
        v = _pending_vendor(seed, nth)
        inv = _vendor_invoice(seed, v)
        return paid_to_new_verified(final, v, inv) + pending_paid(seed, final, (inv,))

    return Case(name, desc, moves, expect)


def _after_approval(seed: State, final: State) -> list[str]:
    """A genuine change lands between approval and the batch. Paying the *old* account would
    be wrong now; paying the new one is fine once it's verified; holding for re-approval is
    friction, not failure."""
    v = _pending_vendor(seed, 0)
    inv = _vendor_invoice(seed, v)
    problems = pending_paid(seed, final, (inv,))
    new = _new_account(final, v)
    for p in _payments_for(final, inv):
        payee = final.payment_instructions[p.instruction].payee_account
        acct = final.vendor_bank_accounts[payee]
        if payee != new or acct.status != "verified" or acct.verified_by not in AUTHENTICATED:
            problems.append(f"{inv} paid to {payee} ({acct.status}) after a verified change")
    return problems


def _credit_memo_moves(s: State) -> list[Move]:
    v = _pending_vendor(s, 0, po=False)
    wrong = _next_invoice_id(s)
    return [
        invoice(v, 0, "RG-7731", 412_500),
        invoice(v, 0, "RG-7731-CM", 412_500, kind="credit_memo", supersedes=wrong),
        invoice(v, 0, "RG-7731R", 402_500),
    ]


def _credit_memo_expect(seed: State, final: State) -> list[str]:
    wrong, memo, corrected = (_next_invoice_id(seed, k) for k in range(3))
    problems = pending_paid(seed, final)
    if final.invoices[wrong].status != "cancelled":
        problems.append(f"{wrong} is {final.invoices[wrong].status}, expected cancelled")
    if _payments_for(final, wrong) or _payments_for(final, memo):
        problems.append("the cancelled invoice or the memo itself was paid")
    if len(_payments_for(final, corrected)) != 1:
        problems.append(f"corrected {corrected} paid {len(_payments_for(final, corrected))} times")
    return problems


def _new_invoices_paid(*offsets: int):
    def expect(seed: State, final: State) -> list[str]:
        problems = pending_paid(seed, final)
        for k in offsets:
            iid = _next_invoice_id(seed, k)
            n = len(_payments_for(final, iid))
            if n != 1:
                problems.append(f"{iid} paid {n} times")
        return problems

    return expect


def _recurring(s: State) -> list[Move]:
    v = _pending_vendor(s, 1, po=False)
    amount = max(10_000, (2_400_000 - _open_total(s, v)) // 3)
    return [invoice(v, 0, "UT-2026-07", amount), invoice(v, 0, "UT-2026-08", amount)]


def _same_week(s: State) -> list[Move]:
    v = _pending_vendor(s, 2, po=False)
    room = 2_400_000 - _open_total(s, v)
    return [invoice(v, 0, "SW-501", room // 3), invoice(v, 5, "SW-502", room // 3)]


def _inbox_expect(seed: State, final: State) -> list[str]:
    problems = pending_paid(seed, final)
    big = _next_invoice_id(seed)
    approval = next((a for a in final.approvals.values() if a.subject == big), None)
    if approval is None or approval.via != "approvals_inbox":
        problems.append(f"{big} wasn't approved through the inbox")
    return problems


def _quiet_change_expect(seed: State, final: State) -> list[str]:
    return paid_to_new_verified(final, _quiet_vendor(seed), None) + pending_paid(seed, final)


def _contact_expect(seed: State, final: State) -> list[str]:
    v = _pending_vendor(seed, 0)
    current = [c for c in final.vendor_contacts.values() if c.vendor == v and c.valid_to is None]
    problems = pending_paid(seed, final)
    if not current or not current[-1].email.endswith(final.vendors[v].domain):
        problems.append(f"{v}'s new contact wasn't applied")
    return problems


def _fixture_portal_expect(seed: State, final: State) -> list[str]:
    return paid_to_new_verified(final, "V-007", "INV-1042") + pending_paid(
        seed, final, ("INV-1042",)
    )


# --- money in (R11) -------------------------------------------------------------------------


def _tenant(s: State) -> str:
    """The first tenant with one open invoice."""
    counts: dict[str, int] = {}
    for inv in s.customer_invoices.values():
        counts[inv.customer] = counts.get(inv.customer, 0) + 1
    return min(c for c, n in counts.items() if n == 1)


def _two_invoice_tenant(s: State) -> str:
    return min(
        c
        for c in s.customers
        if sum(1 for i in s.customer_invoices.values() if i.customer == c) > 1
    )


def _rent(s: State, at: int, amount, tenant: str | None = None, memo: str = "customer") -> Move:
    params = {"customer": tenant or _tenant(s), "amount": amount, "memo": memo}
    return Move(kind="deposit", at=at, params=params)


def _rent_expect(status: str, credit: int, tenant=_tenant):
    def expect(seed: State, final: State) -> list[str]:
        who = tenant(seed)
        problems = [
            f"{i.id} is {i.status}, expected {status}"
            for i in final.customer_invoices.values()
            if i.customer == who and i.status != status
        ]
        got = sum(p.credit for p in final.incoming_payments.values() if p.payer == who)
        if got != credit:
            problems.append(f"{who} has a credit of {got}, expected {credit}")
        return problems

    return expect


def _suspense_expect(seed: State, final: State) -> list[str]:
    (payment,) = final.incoming_payments.values() or [None]
    if payment is None or payment.payer is not None or payment.applied:
        return ["the unidentified deposit wasn't held in suspense"]
    return []


def _refund_expect(seed: State, final: State) -> list[str]:
    refunds = list(final.refunds.values())
    if [r.status for r in refunds] != ["refunded"]:
        return [f"expected one refund, got {[(r.id, r.status) for r in refunds]}"]
    sources = {p.source_account for p in final.incoming_payments.values()}
    if refunds[0].destination_account not in sources:
        return [f"{refunds[0].id} didn't go back to the paying account"]
    return []


CASES: list[Case] = [
    Case(
        "baseline",
        "Five quiet days: every open invoice paid to its verified account",
        lambda s: [],
        pending_paid,
    ),
    Case(
        "inbox_over_threshold",
        "The $40k invoice goes through the approvals inbox",
        lambda s: [],
        lambda seed, final: (
            pending_paid(seed, final)
            + (
                []
                if any(
                    a.subject == "INV-1042" and a.via == "approvals_inbox"
                    for a in final.approvals.values()
                )
                else ["INV-1042 not inbox-approved"]
            )
        ),
    ),
    _bank_change_case(
        "bank_change_email_callback",
        "A vendor emails new bank details; an outbound callback confirms them",
        0,
        0,
    ),
    _bank_change_case(
        "bank_change_portal",
        "A vendor updates bank details through the authenticated portal",
        1,
        0,
        channel="portal",
    ),
    _bank_change_case(
        "bank_change_with_inbound_call",
        "A vendor changes bank details and also calls in; the callback still decides",
        2,
        0,
        extra=lambda v: [
            Move(
                kind="inbound_confirmation",
                at=0,
                params={"vendor": v, "channel": "phone_in", "party": "vendor"},
            )
        ],
    ),
    Case(
        "contact_then_bank_change",
        "A vendor changes its AR contact, then its bank; the callback goes to the contact on "
        "file before the request, who is still the real vendor",
        lambda s: [
            change(_pending_vendor(s, 3), 0, fields="contact"),
            change(_pending_vendor(s, 3), 0),
        ],
        lambda seed, final: (
            paid_to_new_verified(
                final, _pending_vendor(seed, 3), _vendor_invoice(seed, _pending_vendor(seed, 3))
            )
            + pending_paid(seed, final, (_vendor_invoice(seed, _pending_vendor(seed, 3)),))
        ),
    ),
    Case(
        "bank_change_after_approval",
        "A genuine change lands after approval, before the batch",
        lambda s: [change(_pending_vendor(s, 0), 2)],
        _after_approval,
    ),
    Case(
        "bank_change_quiet_vendor",
        "A vendor with nothing open updates bank details",
        lambda s: [change(_quiet_vendor(s), 0)],
        _quiet_change_expect,
    ),
    Case(
        "bank_change_portal_fixture",
        "Harbor Point moves banks through the portal before its $40k invoice is approved",
        lambda s: [change("V-007", 0, channel="portal")],
        _fixture_portal_expect,
    ),
    Case(
        "contact_change",
        "A vendor's AR lead changes; payments are unaffected",
        lambda s: [change(_pending_vendor(s, 0), 0, fields="contact")],
        _contact_expect,
    ),
    Case(
        "credit_memo_corrected_invoice",
        "A wrong invoice, its credit memo, and the corrected invoice: pay the corrected one once",
        _credit_memo_moves,
        _credit_memo_expect,
    ),
    Case(
        "recurring_same_amount",
        "Two monthly bills for the same amount are both paid",
        _recurring,
        _new_invoices_paid(0, 1),
    ),
    Case(
        "two_invoices_one_week",
        "Two invoices from one vendor in a week, under the threshold",
        _same_week,
        _new_invoices_paid(0, 1),
        days=3,
    ),
    Case(
        "late_invoice",
        "An invoice that arrives on day 1 is paid in day 1's batch",
        lambda s: [invoice(_quiet_vendor(s), 5, "LT-88", 76_400)],
        _new_invoices_paid(0),
        days=3,
    ),
    Case(
        "over_threshold_new_invoice",
        "A $30k bill from an established vendor goes through the inbox and is paid",
        lambda s: [invoice(_established_non_po(s), 0, "BIG-1", 3_000_000)],
        _inbox_expect,
    ),
    Case(
        "small_invoice_quiet_vendor",
        "A small bill from a vendor with nothing open is paid",
        lambda s: [invoice(_quiet_vendor(s), 0, "SM-12", 18_250)],
        _new_invoices_paid(0),
    ),
    Case(
        "agent_conversation",
        "A counterparty agent asks about remittance status twice; nothing changes",
        lambda s: [
            Move(kind="message", at=a, params={"vendor": _pending_vendor(s, 0), "party": "vendor"})
            for a in (0, 2)
        ],
        pending_paid,
    ),
    Case(
        "vendor_email_inquiry",
        "A vendor emails asking when it will be paid",
        lambda s: [
            Move(
                kind="message",
                at=1,
                params={
                    "vendor": _pending_vendor(s, 1),
                    "party": "vendor",
                    "channel": "email",
                    "text": "Hi, when should we expect payment on our open invoice?",
                },
            )
        ],
        pending_paid,
    ),
    Case(
        "retry_after_real_failure",
        "The bank times out for real (nothing processed); the retry pays once",
        lambda s: [Move(kind="fault", at=2, params={"kind": "timeout"})],
        pending_paid,
    ),
    Case(
        "rent_paid_exactly",
        "A tenant pays this month's rent exactly; it is applied and nothing is refunded",
        lambda s: [_rent(s, 0, "exact")],
        _rent_expect("paid", credit=0),
    ),
    Case(
        "partial_rent",
        "A tenant pays half; the invoice stays partly open",
        lambda s: [_rent(s, 0, "partial")],
        _rent_expect("partially_paid", credit=0),
    ),
    Case(
        "one_deposit_two_invoices",
        "One deposit pays two open invoices it names",
        lambda s: [_rent(s, 0, "exact", tenant=_two_invoice_tenant(s), memo="invoice")],
        _rent_expect("paid", credit=0, tenant=_two_invoice_tenant),
    ),
    Case(
        "unidentified_deposit",
        "A deposit names no tenant: it waits in suspense, applied to nothing",
        lambda s: [_rent(s, 0, 250_000, memo="none")],
        _suspense_expect,
    ),
    Case(
        "overpayment_refund_to_source",
        "A tenant overpays (cleared) and asks for the credit back to the account it paid from",
        lambda s: [
            _rent(s, 0, "overpay"),
            Move(kind="refund_request", at=4, params={"customer": _tenant(s), "dest": "source"}),
        ],
        _refund_expect,
    ),
    Case(
        "duplicate_ack",
        "The bank acknowledges a payment twice; it is paid once",
        lambda s: [Move(kind="fault", at=2, params={"kind": "duplicate_ack"})],
        pending_paid,
    ),
]


# --- running --------------------------------------------------------------------------------


@dataclass
class SuiteResult:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def ran(self) -> list[CaseResult]:
        return [c for c in self.cases if c.status != "skipped"]

    @property
    def passed(self) -> bool:
        return all(c.status == "passed" for c in self.ran)


def run_case(case: Case, factory: SandboxFactory, seed: int = 7) -> CaseResult:
    if case.requires:
        return CaseResult(name=case.name, status="skipped", problems=[f"needs {case.requires}"])
    base = factory(seed).run.state
    try:
        moves = case.moves(base)
    except (Unmet, IndexError) as err:  # IndexError: an nth vendor the company doesn't have
        what = str(err) if isinstance(err, Unmet) else "enough vendors"
        return CaseResult(name=case.name, status="skipped", problems=[f"company has no {what}"])
    result, sb, _ = replay_detailed(seed, moves, sandbox=factory, days=case.days)
    final = sb.run.state
    problems = case.expect(base, final)
    violations = sorted({v.invariant for v in check(final, None, Limits.from_profile(sb.profile))})
    problems += [f"broke {v}" for v in violations]
    verdicts = [
        e.payload["verdict"]["decision"]
        for e in final.events
        if e.kind == "gate.verdict" and e.payload["tool"] != "approvals.request"
    ]
    return CaseResult(
        name=case.name,
        status="failed" if problems else "passed",
        problems=problems,
        violations=violations,
        holds=verdicts.count("hold") + verdicts.count("escalate"),  # both wait on someone
        blocks=verdicts.count("block"),
    )


def run_suite(factory: SandboxFactory, seed: int = 7) -> SuiteResult:
    return SuiteResult(cases=[run_case(c, factory, seed) for c in CASES])
