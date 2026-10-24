"""R1: a fixed RNG produces the seed state from a company profile.

Determinism rules: only `random.Random(seed)` is used, entities are generated in a fixed order,
and nothing iterates over a set. The same (profile, seed) always gives the same state_hash.
"""

from __future__ import annotations

import random
from typing import Literal

from vandal.contracts.entities import (
    BankAccount,
    Cents,
    Invoice,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
    PaymentInstruction,
    PurchaseOrder,
    Receipt,
    Vendor,
    VendorBankAccount,
    VendorContact,
)
from vandal.twin.profile import Profile, VendorSpec, load_profile
from vandal.twin.state import State

DEFAULT_SEED = 7
NET_TERMS_DAYS = 20  # ~net 30 in business days

FIRST_NAMES = ["Alex", "Jordan", "Sam", "Riley", "Casey", "Morgan", "Taylor", "Jamie", "Drew"]
LAST_NAMES = ["Nguyen", "Garcia", "Patel", "Kim", "Okafor", "Silva", "Cohen", "Ito", "Moreau"]


class _Ids:
    """Sequential business keys: PO-0001, PAY-0001, ..."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    def next(self, prefix: str, width: int = 4) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}-{n:0{width}d}"


def _amount(rng: random.Random, lo: Cents, hi: Cents) -> Cents:
    dollars = rng.randint(lo // 100, hi // 100)
    cents = rng.randint(1, 99) if rng.random() < 0.25 else 0
    return dollars * 100 + cents


def _within_tolerance(rng: random.Random, amount: Cents, tolerance_pct: int) -> Cents:
    """Invoice amount for a PO: exact most of the time, else a small variance inside tolerance."""
    if rng.random() < 0.7:
        return amount
    max_delta = amount * tolerance_pct // 200  # stay within half the tolerance
    return amount + rng.randint(-max_delta, max_delta)


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def seed_state(profile: Profile | None = None, seed: int = DEFAULT_SEED) -> State:
    profile = profile or load_profile()
    rng = random.Random(seed)
    ids = _Ids()
    gen = profile.generation
    state = State(company=profile.company.name, seed=seed, day=0)

    for acct in profile.chart_of_accounts:
        state.ledger_accounts[acct.id] = LedgerAccount(id=acct.id, name=acct.name, kind=acct.kind)
    for ba in profile.bank_accounts:
        state.bank_accounts[ba.id] = BankAccount(
            id=ba.id, name=ba.name, gl_account=ba.gl_account, balance=ba.balance
        )

    _seed_vendors(state, profile, rng, ids)
    _seed_invoices(state, profile, rng, ids)
    _seed_opening_entry(state, profile, ids)

    assert len(state.invoices) == gen.invoices
    return state


def _seed_vendors(state: State, profile: Profile, rng: random.Random, ids: _Ids) -> None:
    history = -profile.generation.history_days
    for spec in profile.vendors:
        state.vendors[spec.id] = Vendor(id=spec.id, name=spec.name, domain=spec.domain)

        contact_from = history * 2
        if rng.random() < profile.generation.prior_contact_rate:
            _add_contact(state, spec, rng, ids, valid_from=history * 4, valid_to=contact_from)
        _add_contact(state, spec, rng, ids, valid_from=contact_from, valid_to=None)

        if rng.random() < profile.generation.prior_account_rate:
            _add_account(state, spec, rng, ids, status="superseded")
        _add_account(state, spec, rng, ids, status="verified")


def _add_contact(
    state: State,
    spec: VendorSpec,
    rng: random.Random,
    ids: _Ids,
    valid_from: int,
    valid_to: int | None,
) -> None:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    cid = ids.next("VC")
    state.vendor_contacts[cid] = VendorContact(
        id=cid,
        vendor=spec.id,
        name=f"{first} {last}",
        email=f"{first.lower()}.{last.lower()}@{spec.domain}",
        phone=f"415-555-{_digits(rng, 4)}",
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _add_account(
    state: State,
    spec: VendorSpec,
    rng: random.Random,
    ids: _Ids,
    status: Literal["verified", "superseded"],
) -> None:
    aid = ids.next("BA")
    state.vendor_bank_accounts[aid] = VendorBankAccount(
        id=aid,
        vendor=spec.id,
        routing="1210" + _digits(rng, 5),
        account=_digits(rng, 10),
        status=status,
        source="vendor_onboarding",
        verified_by="phone_outbound",
    )


def _seed_invoices(state: State, profile: Profile, rng: random.Random, ids: _Ids) -> None:
    gen = profile.generation
    matrix = profile.approval_matrix
    vendors = {v.id: v for v in profile.vendors}
    fixtures = profile.fixtures

    # Which vendor each generated invoice belongs to. Every vendor gets at least one paid
    # invoice; fixture vendors get enough history for the simulated approver.
    history_slots = gen.invoices - gen.pending_invoices
    history_vendors = [v.id for v in profile.vendors]
    for vid, n in fixtures.min_prior_payments.items():
        history_vendors += [vid] * (n - 1)
    while len(history_vendors) < history_slots:
        history_vendors.append(rng.choice(profile.vendors).id)
    rng.shuffle(history_vendors)

    pending_slots = gen.pending_invoices - len(fixtures.invoices)
    # Pending generated invoices stay under the approval threshold; fixtures cover the big ones.
    pending_vendors = [rng.choice(profile.vendors).id for _ in range(pending_slots)]

    reserved = {f.id for f in fixtures.invoices}
    next_number = 1001

    def next_invoice_id() -> str:
        nonlocal next_number
        while f"INV-{next_number}" in reserved:
            next_number += 1
        iid = f"INV-{next_number}"
        next_number += 1
        return iid

    plan: list[tuple[str, int, int, bool]] = []  # (vendor, received_on, due, paid)
    for vid in history_vendors:
        received = rng.randint(-gen.history_days, -NET_TERMS_DAYS - 1)
        plan.append((vid, received, received + NET_TERMS_DAYS, True))
    for vid in pending_vendors:
        received = rng.randint(-10, -1)
        plan.append((vid, received, rng.randint(1, 10), False))
    plan.sort(key=lambda p: (p[1], p[0]))
    numbers: dict[str, int] = {}  # per-vendor invoice number sequence, random start

    for vid, received, due, paid in plan:
        spec = vendors[vid]
        hi = spec.max if paid else min(spec.max, matrix.threshold - 1)
        po_amount = _amount(rng, spec.min, hi)
        amount = _within_tolerance(rng, po_amount, matrix.match_tolerance_pct)
        if not paid:
            amount = min(amount, matrix.threshold - 1)
        _add_invoice(
            state,
            rng,
            ids,
            iid=next_invoice_id(),
            spec=spec,
            number=_next_number(numbers, spec, rng),
            amount=amount,
            po_amount=po_amount if spec.po else None,
            dimension=rng.choice(profile.properties).id,
            received_on=received,
            due_date=due,
            paid=paid,
        )

    for fx in fixtures.invoices:
        _add_invoice(
            state,
            rng,
            ids,
            iid=fx.id,
            spec=vendors[fx.vendor],
            number=fx.number,
            amount=fx.amount,
            po_amount=fx.amount if fx.po else None,
            dimension=fx.dimension,
            received_on=fx.received_on,
            due_date=fx.due_date,
            paid=False,
        )

    state.invoices = dict(sorted(state.invoices.items()))


def _next_number(numbers: dict[str, int], spec: VendorSpec, rng: random.Random) -> str:
    if spec.id not in numbers:
        numbers[spec.id] = rng.randint(1000, 8000)
    numbers[spec.id] += 1
    return f"{spec.domain[:3].upper()}{spec.id[-2:]}-{numbers[spec.id]}"


def _add_invoice(
    state: State,
    rng: random.Random,
    ids: _Ids,
    *,
    iid: str,
    spec: VendorSpec,
    number: str,
    amount: Cents,
    po_amount: Cents | None,
    dimension: str,
    received_on: int,
    due_date: int,
    paid: bool,
) -> None:
    po_id = None
    if po_amount is not None:
        po_id = ids.next("PO")
        issued = received_on - rng.randint(5, 15)
        state.purchase_orders[po_id] = PurchaseOrder(
            id=po_id, vendor=spec.id, amount=po_amount, dimension=dimension, issued_on=issued
        )
        rc_id = ids.next("RC")
        state.receipts[rc_id] = Receipt(
            id=rc_id,
            po=po_id,
            amount=po_amount,
            received_on=rng.randint(issued + 1, received_on),
        )

    state.invoices[iid] = Invoice(
        id=iid,
        vendor=spec.id,
        number=number,
        po=po_id,
        amount=amount,
        dimension=dimension,
        received_on=received_on,
        due_date=due_date,
        status="paid" if paid else "received",
    )
    if not paid:
        return

    account = next(
        a.id
        for a in reversed(state.vendor_bank_accounts.values())
        if a.vendor == spec.id and a.status == "verified"
    )
    pi_id = ids.next("PI")
    state.payment_instructions[pi_id] = PaymentInstruction(
        id=pi_id, invoice=iid, amount=amount, payee_account=account
    )
    pay_id = ids.next("PAY")
    state.payments[pay_id] = Payment(
        id=pay_id, instruction=pi_id, status="settled", attempts=1, settled_on=due_date
    )


def _seed_opening_entry(state: State, profile: Profile, ids: _Ids) -> None:
    """History is pre-opening: day 0 opens with bank balances against equity, and AP at zero."""
    lines = [JournalLine(account=b.gl_account, debit=b.balance) for b in profile.bank_accounts]
    total = sum(b.balance for b in profile.bank_accounts)
    lines.append(JournalLine(account=profile.opening_equity_account, credit=total))
    state.journal.append(
        JournalEntry(id=ids.next("JE"), posted_on=0, lines=lines, memo="Opening balances")
    )


def summary(state: State, profile: Profile) -> str:
    pending = [i for i in state.invoices.values() if i.status == "received"]
    paid = [i for i in state.invoices.values() if i.status == "paid"]
    verified = sum(1 for a in state.vendor_bank_accounts.values() if a.status == "verified")

    def usd(cents: Cents) -> str:
        return f"${cents / 100:,.2f}"

    caps = profile.attacker_capabilities
    risk = profile.risk_appetite
    rows = [
        f"{state.company}  (seed {state.seed}, starts {profile.company.start_date})",
        f"  properties        {len(profile.properties)}",
        f"  vendors           {len(state.vendors)}  "
        f"({len(state.vendor_contacts)} contacts, {verified} verified accounts)",
        f"  purchase orders   {len(state.purchase_orders)}  ({len(state.receipts)} receipts)",
        f"  invoices          {len(state.invoices)}  "
        f"({len(paid)} paid history, {len(pending)} pending, "
        f"{usd(sum(i.amount for i in pending))} open)",
        f"  payments          {len(state.payments)} settled",
    ]
    for ba in state.bank_accounts.values():
        rows.append(f"  bank {ba.name:<12} {usd(ba.balance)}")
    rows += [
        f"  approval above    {usd(profile.approval_matrix.threshold)}",
        f"  attacker          channels={','.join(caps.change_request_channels)} "
        f"spoof_caller_id={caps.spoof_caller_id} clone_voice={caps.clone_voice} "
        f"portal_takeover={caps.portal_takeover}",
        f"  risk appetite     lambda={usd(risk.lambda_per_blocked)} mu={usd(risk.mu_per_hold)}",
        f"  state_hash        {state.state_hash()}",
    ]
    return "\n".join(rows)
