"""Twin entities (DESIGN 5.1), keyed by stable business keys so traces replay on any clone.

Money is integer cents everywhere. Dates are sim business days (int), never wall-clock time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr

Cents = int
SimDay = int  # business day index on the sim clock


class Entity(BaseModel):
    """Immutable. Change an entity with State.update(), which swaps in a copy.

    Clones share entity objects (structural sharing), so in-place edits, including edits to
    nested lists and dicts, would leak into every other state. Frozen makes that an error.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str

    # Cached sha256 of model_dump_json(). Safe because the entity never changes.
    _digest: str | None = PrivateAttr(default=None)


# --- Actors ---------------------------------------------------------------------------------


class Actor(BaseModel):
    """Who is calling a tool. Roles drive segregation of duties (DESIGN 6.1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    role: Literal["operator", "approver", "gate", "synthesizer", "tools", "external", "system"]


# --- Vendors --------------------------------------------------------------------------------


class Vendor(Entity):  # V-007
    name: str
    status: Literal["active", "inactive", "blocked"] = "active"
    domain: str
    gl_account: str  # default expense account
    po_required: bool = True  # bills against POs (3-way match applies)


class VendorContact(Entity):
    vendor: str
    name: str
    email: str
    phone: str
    valid_from: SimDay
    valid_to: SimDay | None = None


class VendorBankAccount(Entity):  # BA-…
    vendor: str
    routing: str
    account: str
    status: Literal["verified", "unverified", "superseded", "rejected"]
    source: str
    verified_by: str | None = None
    verified_on: SimDay | None = None


EvidenceChannel = Literal["email", "portal", "agent_msg", "phone_in", "phone_outbound", "video"]


class Evidence(Entity):  # EVD-…: verification of a change request (R6)
    change_request: str
    channel: EvidenceChannel
    direction: Literal["inbound", "outbound"]
    received_on: SimDay
    status: Literal["pending", "answered"] = "answered"  # an outbound callback starts pending
    confirms: bool | None = None  # did the other party confirm the change?
    contact: str | None = None  # the contact dialed (outbound) or claimed (inbound)
    phone: str | None = None
    contact_as_of: SimDay | None = None  # the day whose contact record was used
    authenticated: bool = False  # outbound to a number on file, or an authenticated portal
    voice_match: int | None = None  # percent, for inbound calls and video
    message: str | None = None


class VendorChangeRequest(Entity):  # CR-…
    vendor: str
    fields: Literal["bank", "contact"] = "bank"
    proposed: dict[str, str]
    channel: Literal["email", "portal", "agent_msg"]
    sender: str
    message: str | None = None  # the channel message it came from
    received_on: SimDay
    status: Literal["open", "held", "applied", "rejected"] = "open"
    evidence: list[str] = []


# --- Obligations ----------------------------------------------------------------------------


class PurchaseOrder(Entity):  # PO-…
    vendor: str
    amount: Cents
    dimension: str
    issued_on: SimDay


class Receipt(Entity):  # RC-…
    po: str
    amount: Cents
    received_on: SimDay


InvoiceStatus = Literal[
    "received", "validated", "approved", "scheduled", "paid", "held", "rejected"
]


class Invoice(Entity):  # INV-…
    vendor: str
    number: str
    po: str | None = None
    amount: Cents
    dimension: str
    received_on: SimDay
    due_date: SimDay
    kind: Literal["invoice", "credit_memo"] = "invoice"
    supersedes: str | None = None
    status: InvoiceStatus = "received"
    scheduled_for: SimDay | None = None


class ApprovedInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invoice: str
    amount: Cents
    payee_account: str
    currency: str = "USD"
    due_date: SimDay


class ApprovalRequest(Entity):  # AQ-…: waiting in the approvals inbox
    subject: str
    requested_by: str
    instruction: ApprovedInstruction
    status: Literal["pending", "approved", "denied"] = "pending"
    decided_by: str | None = None
    reason: str = ""


class Approval(Entity):  # APR-…
    subject: str
    requested_by: str
    approver: str
    via: Literal["approvals_inbox", "policy"] = "approvals_inbox"  # policy = gate, under threshold
    approved_instruction: ApprovedInstruction
    instruction_hash: str


# --- Execution ------------------------------------------------------------------------------


class PaymentInstruction(Entity):  # PI-…
    invoice: str
    amount: Cents
    payee_account: str
    idempotency_key: str | None = None


class Payment(Entity):  # PAY-…
    instruction: str
    status: Literal[
        "scheduled", "submitted", "acknowledged", "settled", "failed", "recalled", "misdirected"
    ] = "scheduled"
    attempts: int = 0
    submitted_on: SimDay | None = None
    settled_on: SimDay | None = None


class BankAccount(Entity):  # CB-…: the company's own accounts
    name: str
    gl_account: str
    balance: Cents


class BankTransaction(Entity):  # BT-…
    bank_account: str
    amount: Cents  # positive in, negative out
    posted_on: SimDay
    payment: str | None = None
    counterparty_account: str | None = None
    reconciled: bool = False


# --- Money in -------------------------------------------------------------------------------


class Customer(Entity):  # C-…
    name: str


class CustomerInvoice(Entity):  # AR-…
    customer: str
    amount: Cents
    due_date: SimDay
    status: Literal["open", "partially_paid", "paid", "overpaid"] = "open"


class IncomingPayment(Entity):  # IN-…
    bank_transaction: str
    payer: str | None = None
    source_account: str
    amount: Cents
    remittance: str = ""
    applied: dict[str, Cents] = {}  # customer invoice id -> cents applied


class Refund(Entity):  # RF-…
    customer: str
    amount: Cents
    destination_account: str
    reason: str
    approval: str | None = None
    status: Literal["requested", "approved", "refunded", "rejected"] = "requested"


# --- Ledger ---------------------------------------------------------------------------------


class LedgerAccount(Entity):
    name: str
    kind: Literal["asset", "liability", "equity", "revenue", "expense"]


class JournalLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account: str
    debit: Cents = 0
    credit: Cents = 0


class JournalEntry(Entity):  # append-only
    posted_on: SimDay
    lines: list[JournalLine]
    memo: str = ""
    reverses_entry_id: str | None = None


# --- Operations -----------------------------------------------------------------------------


class Case(Entity):
    kind: Literal["exception", "recovery", "escalation"]
    subject: str
    reason: str
    rationale: str = ""
    status: Literal["open", "resolved"] = "open"


class OracleLabel(BaseModel):
    """Harness-only ground truth. Lives in verify/oracle.py; Tools can never read it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    label: Literal["attacker_controlled", "true_sender", "deepfake", "duplicate_of"]
    value: str | bool = True
