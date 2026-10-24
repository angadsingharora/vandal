"""O1: the planted messy-data items (DESIGN 5.6) and their answer key.

A clean seed makes intake trivial. Here every pending seeded invoice is rendered as the document
it arrived as: an email body, OCR'd PDF text with typos, a forwarded thread with the invoice three
replies down, or a structured line-item table. Each rendering carries a `Truth` (what the Operator
should extract and how it should code the GL), which lives here in verify/ where no Operator can
read it (tests/test_oracle.py). `score()` runs an extractor over the items and reports field and
GL-coding accuracy for the scorecard.

Some items describe work that belongs to a different expense account than the vendor's default
(a plumber installing a new water heater is a capital improvement), so GL coding has to read the
document, not just the vendor master. Amounts and keys come from the seed; the text is ours.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents, Invoice
from vandal.contracts.events import ChannelEvent
from vandal.twin.profile import Profile
from vandal.twin.state import State

Format = Literal["email_body", "ocr_text", "forwarded_thread", "line_items"]
FORMATS: tuple[Format, ...] = ("email_body", "ocr_text", "forwarded_thread", "line_items")
FIELDS = ("vendor", "number", "amount", "po", "dimension")
GL_TWIST_EVERY = 4  # every nth item describes work outside the vendor's default account

Extractor = Callable[[ChannelEvent, State], Mapping[str, Any]]
"""What the scorecard scores: (message, state) -> {vendor, number, amount, po, dimension,
gl_account, source?}. verify/ can't import operator/, so the composition root passes it in."""

# What the work on an invoice looks like, by expense account. The vendor's default account picks
# the usual phrasing; a twist picks a phrase from another account.
WORK: dict[str, list[str]] = {
    "5100": [
        "emergency leak repair, unit 4B",
        "service call and repair of the failed rooftop unit",
        "repair of damaged entry door and frame",
        "replace broken fixtures, 2nd floor restroom",
    ],
    "5200": ["monthly utility service", "water and sewer service, billing period"],
    "5300": ["monthly landscape maintenance", "irrigation repair and grounds care"],
    "5400": ["security patrol coverage, nights and weekends", "access control monitoring"],
    "5500": ["janitorial service, common areas", "night cleaning crew, lobby and corridors"],
    "5600": ["property insurance premium, quarterly installment"],
    "5700": ["legal services, lease review", "professional fees, consultation"],
    "5800": [
        "capital improvement: installation of a new rooftop HVAC unit",
        "capital project: lobby renovation, phase 1",
        "capital improvement: new water heater installation",
    ],
    "5900": ["software subscription, annual", "IT support and software licenses"],
    "5950": ["waste removal and recycling service"],
}
TWIST: dict[str, str] = {"5100": "5800", "5800": "5100", "5300": "5100", "5500": "5100"}


class Truth(BaseModel):
    """The answer key for one planted item. Harness-only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vendor: str
    number: str
    amount: Cents
    po: str | None
    dimension: str
    gl_account: str
    invoice: str  # the seeded invoice this document renders


class MessyItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    format: Format
    message: ChannelEvent
    truth: Truth
    twisted: bool  # the work belongs to an account other than the vendor's default


class IntakeAccuracy(BaseModel):
    """Field and GL-coding accuracy over the planted items (DESIGN 10.1)."""

    model_config = ConfigDict(extra="forbid")

    items: int
    fields_total: int
    fields_correct: int
    gl_total: int
    gl_correct: int
    by_format: dict[str, float]  # field accuracy per document format
    sources: dict[str, int]  # how many items each extraction path answered (llm, deterministic)
    misses: list[str]  # "<item> <field>: got X, want Y"

    @property
    def extraction_accuracy(self) -> float:
        return self.fields_correct / self.fields_total if self.fields_total else 0.0

    @property
    def gl_coding_accuracy(self) -> float:
        return self.gl_correct / self.gl_total if self.gl_total else 0.0


# --- the items ------------------------------------------------------------------------------


def messy_items(state: State, profile: Profile) -> list[MessyItem]:
    """One document per pending seeded invoice, formats cycled so each gets a handful. The
    rendering is a pure function of the seed state, so items replay identically."""
    rng = random.Random(f"messy|{state.seed}")
    pending = sorted(
        (i for i in state.invoices.values() if i.status == "received" and i.kind == "invoice"),
        key=lambda i: i.id,
    )
    properties = {p.id: p.name for p in profile.properties}
    items = []
    for n, inv in enumerate(pending):
        fmt = FORMATS[n % len(FORMATS)]
        vendor = state.vendors[inv.vendor]
        twisted = n % GL_TWIST_EVERY == GL_TWIST_EVERY - 1 and vendor.gl_account in TWIST
        gl = TWIST[vendor.gl_account] if twisted else vendor.gl_account
        work = rng.choice(WORK[gl])
        contact = next(
            (
                c
                for c in state.vendor_contacts.values()
                if c.vendor == inv.vendor and c.valid_to is None
            ),
            None,
        )
        doc = _Doc(
            inv=inv,
            vendor_name=vendor.name,
            domain=vendor.domain,
            contact_name=contact.name if contact else "Accounts Receivable",
            contact_email=contact.email if contact else f"billing@{vendor.domain}",
            contact_phone=contact.phone if contact else "415-555-0100",
            property_name=properties.get(inv.dimension, inv.dimension),
            work=work,
            rng=rng,
        )
        subject, body, channel, attachments = RENDER[fmt](doc)
        item_id = f"MSY-{n + 1:03d}"
        items.append(
            MessyItem(
                id=item_id,
                format=fmt,
                message=ChannelEvent(
                    id=item_id,
                    day=max(inv.received_on, 0),
                    channel=channel,
                    sender=doc.contact_email,
                    subject=subject,
                    body=body,
                    attachments=attachments,
                ),
                truth=Truth(
                    vendor=inv.vendor,
                    number=inv.number,
                    amount=inv.amount,
                    po=inv.po,
                    dimension=inv.dimension,
                    gl_account=gl,
                    invoice=inv.id,
                ),
                twisted=twisted,
            )
        )
    return items


class _Doc(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    inv: Invoice
    vendor_name: str
    domain: str
    contact_name: str
    contact_email: str
    contact_phone: str
    property_name: str
    work: str
    rng: random.Random


def _money(cents: Cents) -> str:
    return f"${cents / 100:,.2f}"


def _email_body(d: _Doc) -> tuple[str, str, str, list[str]]:
    po = f"This bills against your purchase order {d.inv.po}.\n" if d.inv.po else ""
    body = (
        f"Hi Bayline AP team,\n\n"
        f"Please find attached invoice {d.inv.number} from {d.vendor_name} for the "
        f"{d.work} at {d.property_name}.\n"
        f"Amount due: {_money(d.inv.amount)}. Terms: Net 20.\n{po}\n"
        f"Let me know if you need anything else to process this.\n\n"
        f"Thanks,\n{d.contact_name}\n{d.vendor_name} | {d.contact_phone}\n"
    )
    return f"Invoice {d.inv.number} - {d.vendor_name}", body, "email", ["invoice.pdf"]


OCR_SWAPS = {"O": "0", "l": "1", "I": "1", "S": "5", "B": "8", "e": "c", "m": "rn"}


def _ocr(text: str, rng: random.Random) -> str:
    """OCR noise: in words made only of letters, a few characters come back as look-alikes, and
    the odd space lands inside a word. Digits, codes, and amounts are left alone."""
    out = []
    for token in text.split(" "):
        if token.isalpha() and len(token) >= 4 and rng.random() < 0.35:
            chars = list(token)
            for _ in range(rng.randint(1, 2)):
                i = rng.randrange(len(chars))
                chars[i] = OCR_SWAPS.get(chars[i], chars[i])
            if rng.random() < 0.15:
                i = rng.randrange(1, len(chars))
                chars.insert(i, " ")
            token = "".join(chars)
        out.append(token)
    return " ".join(out)


def _ocr_text(d: _Doc) -> tuple[str, str, str, list[str]]:
    po_line = f"PO Number: {d.inv.po}\n" if d.inv.po else "PO Number: n/a\n"
    page = (
        f"{d.vendor_name.upper()}\n{d.domain}  |  {d.contact_phone}\n\n"
        f"INVOICE\n"
        f"Invoice No: {d.inv.number}\n"
        f"Bill To: Bayline Property Group\n"
        f"Property: {d.property_name}\n"
        f"{po_line}\n"
        f"Description                                   Amount\n"
        f"{d.work}    {_money(d.inv.amount)}\n\n"
        f"                       Subtotal   {_money(d.inv.amount)}\n"
        f"                       Tax        $0.00\n"
        f"                       TOTAL DUE  {_money(d.inv.amount)}\n\n"
        f"Please remit within 20 days. Thank you for your business.\n"
    )
    body = "\n".join(_ocr(line, d.rng) for line in page.split("\n"))
    return f"Scanned invoice from {d.vendor_name}", body, "email", ["scan_0001.pdf"]


def _forwarded_thread(d: _Doc) -> tuple[str, str, str, list[str]]:
    estimate = d.inv.amount + d.rng.choice([-1, 1]) * d.rng.randint(5_000, 40_000)
    ticket = d.rng.randint(4000, 9999)
    po = f" PO {d.inv.po} covers it." if d.inv.po else ""
    body = (
        f"Can you handle this one? Approved on my end; the work is done.\n\n"
        f"Morgan\n\n"
        f"> From: Site lead, {d.property_name}\n"
        f"> Forwarding, the vendor says this is overdue. Ticket #{ticket}. I remember the "
        f"estimate being around {_money(estimate)} but the invoice is below.\n"
        f">\n"
        f">> From: {d.contact_name} <{d.contact_email}>\n"
        f">> Subject: Invoice {d.inv.number}\n"
        f">>\n"
        f">> Hi, resending invoice {d.inv.number} for the {d.work} at {d.property_name}.\n"
        f">> Total due: {_money(d.inv.amount)}.{po}\n"
        f">> Thanks, {d.contact_name}, {d.vendor_name}\n"
    )
    return f"FW: FW: Re: Invoice {d.inv.number}", body, "email", []


def _line_items(d: _Doc) -> tuple[str, str, str, list[str]]:
    first = d.inv.amount * d.rng.randint(30, 70) // 100
    second = d.inv.amount - first
    other = d.rng.choice(["materials and parts", "labor, standard rate", "trip charge and permits"])
    po = d.inv.po or "none"
    body = (
        f"INVOICE {d.inv.number}\n"
        f"Vendor: {d.vendor_name}    PO: {po}    Property: {d.property_name}\n\n"
        f"Qty  Description                                      Amount\n"
        f"  1  {d.work:<45} {_money(first):>12}\n"
        f"  1  {other:<45} {_money(second):>12}\n\n"
        f"     Subtotal {_money(d.inv.amount):>45}\n"
        f"     Tax (0%)  {'$0.00':>44}\n"
        f"     Total {_money(d.inv.amount):>48}\n"
    )
    return f"Portal submission: invoice {d.inv.number}", body, "portal", []


RENDER: dict[Format, Callable[[_Doc], tuple[str, str, str, list[str]]]] = {
    "email_body": _email_body,
    "ocr_text": _ocr_text,
    "forwarded_thread": _forwarded_thread,
    "line_items": _line_items,
}


# --- scoring --------------------------------------------------------------------------------


def score(items: list[MessyItem], extract: Extractor, state: State) -> IntakeAccuracy:
    fields_total = fields_correct = gl_total = gl_correct = 0
    per_format: dict[str, list[int]] = {}
    sources: dict[str, int] = {}
    misses = []
    for item in items:
        got = extract(item.message, state)
        want = item.truth.model_dump()
        hits = per_format.setdefault(item.format, [0, 0])
        for field in FIELDS:
            fields_total += 1
            hits[1] += 1
            if got.get(field) == want[field]:
                fields_correct += 1
                hits[0] += 1
            else:
                misses.append(f"{item.id} {field}: got {got.get(field)!r}, want {want[field]!r}")
        gl_total += 1
        if got.get("gl_account") == want["gl_account"]:
            gl_correct += 1
        else:
            misses.append(
                f"{item.id} gl_account: got {got.get('gl_account')!r}, want {want['gl_account']!r}"
            )
        source = str(got.get("source", "unknown"))
        sources[source] = sources.get(source, 0) + 1
    return IntakeAccuracy(
        items=len(items),
        fields_total=fields_total,
        fields_correct=fields_correct,
        gl_total=gl_total,
        gl_correct=gl_correct,
        by_format={f: (c / t if t else 0.0) for f, (c, t) in sorted(per_format.items())},
        sources=sources,
        misses=misses,
    )


def reopen_as_message(state: State, item: MessyItem) -> None:
    """Make the seeded invoice arrive as its document instead: drop the structured copy so the
    Operator has to receive it from the message. The PO and receipt stay. For tests and demos."""
    state.invoices.pop(item.truth.invoice, None)
