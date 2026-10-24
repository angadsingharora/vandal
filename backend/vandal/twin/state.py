"""R1: State, clone(), update(), entity_hash(), state_hash().

State holds every twin entity keyed by its stable business key. Nothing here reads the wall clock
or Python's randomized hash(), so the same seed and events give the same hash in any process.

Performance model (search runs thousands of these, IMPLEMENTATION R4):
- Entities are frozen and shared between clones. clone() copies only the containers.
- A state is changed only through update() / put(), and only by its owner: a fresh clone().
- entity_hash() covers the entities, not the event log, so two paths that reach the same
  company state dedupe. Each entity's digest is cached on the (immutable) entity.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import (
    Approval,
    ApprovalRequest,
    BankAccount,
    BankTransaction,
    Case,
    Customer,
    CustomerInvoice,
    Entity,
    Evidence,
    IncomingPayment,
    Invoice,
    JournalEntry,
    LedgerAccount,
    Payment,
    PaymentInstruction,
    PurchaseOrder,
    Receipt,
    Refund,
    SimDay,
    Vendor,
    VendorBankAccount,
    VendorChangeRequest,
    VendorContact,
)
from vandal.contracts.events import Event


class State(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = ""
    seed: int = 0
    day: SimDay = 0

    vendors: dict[str, Vendor] = {}
    vendor_contacts: dict[str, VendorContact] = {}
    vendor_bank_accounts: dict[str, VendorBankAccount] = {}
    change_requests: dict[str, VendorChangeRequest] = {}
    evidence: dict[str, Evidence] = {}

    purchase_orders: dict[str, PurchaseOrder] = {}
    receipts: dict[str, Receipt] = {}
    invoices: dict[str, Invoice] = {}
    approval_requests: dict[str, ApprovalRequest] = {}
    approvals: dict[str, Approval] = {}

    payment_instructions: dict[str, PaymentInstruction] = {}
    payments: dict[str, Payment] = {}
    bank_accounts: dict[str, BankAccount] = {}
    bank_transactions: dict[str, BankTransaction] = {}

    customers: dict[str, Customer] = {}
    customer_invoices: dict[str, CustomerInvoice] = {}
    incoming_payments: dict[str, IncomingPayment] = {}
    refunds: dict[str, Refund] = {}

    ledger_accounts: dict[str, LedgerAccount] = {}
    journal: list[JournalEntry] = []
    cases: dict[str, Case] = {}

    events: list[Event] = []

    def clone(self) -> State:
        """O(number of entities) container copy; entity objects are shared, never copied."""
        data: dict[str, Any] = {name: getattr(self, name) for name in _SCALARS}
        for name in _COLLECTIONS:
            data[name] = dict(getattr(self, name))
        data["journal"] = list(self.journal)
        data["events"] = list(self.events)
        return State.model_construct(**data)

    def put(self, collection: str, entity: Entity) -> None:
        """Insert or replace an entity. Call only on a state you own (a fresh clone)."""
        getattr(self, collection)[entity.id] = entity

    def update(self, collection: str, key: str, **changes: Any) -> Entity:
        """Swap in a changed copy of one entity. Call only on a state you own."""
        items = getattr(self, collection)
        new = items[key].model_copy(update=changes)
        new._digest = None  # model_copy carries private attrs over; the copy differs
        items[key] = new
        return new

    def entity_hash(self) -> str:
        """Hash of the company state, without the event log: the search dedup key.

        Collections hash in sorted-key order, so insertion order doesn't matter. The journal
        keeps its posting order.
        """
        h = hashlib.sha256(f"{self.company}|{self.day}".encode())
        for name in _COLLECTIONS:
            h.update(f"#{name}".encode())
            items = getattr(self, name)
            for key in sorted(items):
                h.update(_digest(items[key]).encode())
        h.update(b"#journal")
        for entry in self.journal:
            h.update(_digest(entry).encode())
        return h.hexdigest()

    def state_hash(self) -> str:
        """Hash of everything, including the seed and the event log: the replay identity."""
        h = hashlib.sha256(f"{self.seed}|{self.entity_hash()}".encode())
        for event in self.events:
            h.update(event.model_dump_json().encode())
        return h.hexdigest()


_SCALARS = ("company", "seed", "day")
_COLLECTIONS = tuple(
    name
    for name, field in State.model_fields.items()
    if field.annotation is not None and getattr(field.annotation, "__origin__", None) is dict
)


def _digest(entity: Entity) -> str:
    digest = entity._digest
    if digest is None:
        digest = hashlib.sha256(entity.model_dump_json().encode()).hexdigest()
        entity._digest = digest
    return digest
