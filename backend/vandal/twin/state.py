"""R1: State, clone(), state_hash().

State holds every twin entity keyed by its stable business key. Nothing here reads the wall clock
or Python's randomized hash(), so the same seed and events give the same hash in any process.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import (
    Approval,
    BankAccount,
    BankTransaction,
    Case,
    Customer,
    CustomerInvoice,
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
        return self.model_copy(deep=True)

    def state_hash(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
