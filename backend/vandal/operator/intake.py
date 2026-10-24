"""O1: intake. Classify a channel event, extract its fields, match the vendor and PO, code the
GL, and say what to do about it.

Two paths give the same `Extraction`:

  - Claude (MODEL_AGENT, through vandal/llm.py) reads the message with the vendor master, the
    properties, the open POs, and the expense accounts, and answers as structured output. Every
    id it names is checked against the twin; a field that doesn't resolve falls back.
  - A deterministic reader (`extract_deterministic`) does the same job from patterns: sender
    domain and vendor names, invoice-number shapes, labeled totals, PO references, property
    names, and the words that describe the work. It's what runs when there's no model, and what
    fills any field the model got wrong.

Money outcomes never depend on which path ran: whatever intake proposes goes through Blue.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.events import ChannelEvent
from vandal.twin.profile import Profile
from vandal.twin.state import State

PROMPT_VERSION = "o1-intake-1"
Intent = Literal[
    "invoice",
    "credit_memo",
    "vendor_bank_change",
    "vendor_contact_change",
    "payment_inquiry",
    "other",
]

SYSTEM = (
    "You are the intake step of an accounts-payable agent for a property manager. Read one "
    "inbound message and return structured fields. Use only ids from the reference data given "
    "(vendor ids, PO ids, property ids, expense account ids). Amounts are integer cents. If a "
    "field isn't in the message, return null. Code the GL from the work described, not from "
    "who sent it: repairs and service calls are repairs, installations of new equipment and "
    "renovations are capital improvements."
)


class Extraction(BaseModel):
    """What intake read from one message. Field names match verify/messy.FIELDS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Intent
    vendor: str | None = None
    number: str | None = None
    amount: int | None = None  # cents
    po: str | None = None
    dimension: str | None = None
    gl_account: str | None = None
    supersedes: str | None = None  # credit memo: the invoice it corrects (by number)
    due_in_days: int = 5
    routing: str | None = None  # bank change
    account: str | None = None
    contact_name: str | None = None  # contact change
    contact_email: str | None = None
    contact_phone: str | None = None
    source: Literal["llm", "deterministic", "mixed"] = "deterministic"


class _LLMExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    vendor: str | None = None
    number: str | None = None
    amount: int | None = None
    po: str | None = None
    dimension: str | None = None
    gl_account: str | None = None
    supersedes: str | None = None
    routing: str | None = None
    account: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


def extract(ev: ChannelEvent, state: State, profile: Profile, use_llm: bool = True) -> Extraction:
    base = extract_deterministic(ev, state, profile)
    if not use_llm:
        return base
    from vandal.llm import LLMUnavailable, structured

    try:
        reply = structured(
            agent="operator",
            step="intake",
            prompt_version=PROMPT_VERSION,
            system=SYSTEM,
            prompt=json.dumps(_context(ev, state, profile), sort_keys=True),
            schema=_LLMExtraction,
            model_env="MODEL_AGENT",
        )
    except LLMUnavailable:
        return base
    return _merge(reply, base, state, profile)


def _context(ev: ChannelEvent, state: State, profile: Profile) -> dict[str, Any]:
    return {
        "message": {
            "channel": ev.channel,
            "sender": ev.sender,
            "subject": ev.subject,
            "body": ev.body,
            "attachments": ev.attachments,
        },
        "vendors": [
            {"id": v.id, "name": v.name, "domain": v.domain, "default_gl": v.gl_account}
            for v in state.vendors.values()
        ],
        "properties": [{"id": p.id, "name": p.name} for p in profile.properties],
        "open_pos": [
            {"id": po.id, "vendor": po.vendor, "amount": po.amount, "dimension": po.dimension}
            for po in state.purchase_orders.values()
            if not any(i.po == po.id and i.status != "received" for i in state.invoices.values())
        ],
        "expense_accounts": [
            {"id": a.id, "name": a.name}
            for a in state.ledger_accounts.values()
            if a.kind == "expense"
        ],
    }


def _merge(reply: _LLMExtraction, base: Extraction, state: State, profile: Profile) -> Extraction:
    """Keep every model answer that resolves in the twin; fill the rest from the deterministic
    reader. The model's intent wins unless it names nothing usable."""
    props = {p.id for p in profile.properties}
    expenses = {a.id for a in state.ledger_accounts.values() if a.kind == "expense"}
    fields: dict[str, Any] = {}
    fields["vendor"] = reply.vendor if reply.vendor in state.vendors else base.vendor
    fields["po"] = reply.po if reply.po in state.purchase_orders else base.po
    fields["dimension"] = reply.dimension if reply.dimension in props else base.dimension
    fields["gl_account"] = reply.gl_account if reply.gl_account in expenses else base.gl_account
    fields["number"] = reply.number or base.number
    fields["amount"] = reply.amount if reply.amount and reply.amount > 0 else base.amount
    for name in (
        "supersedes",
        "routing",
        "account",
        "contact_name",
        "contact_email",
        "contact_phone",
    ):
        fields[name] = getattr(reply, name) or getattr(base, name)
    used_model = any(fields[k] == getattr(reply, k) for k in fields if fields[k] is not None)
    return Extraction(
        intent=reply.intent,
        due_in_days=base.due_in_days,
        source="llm"
        if used_model and fields == _fields(reply)
        else "mixed"
        if used_model
        else "deterministic",
        **fields,
    )


def _fields(reply: _LLMExtraction) -> dict[str, Any]:
    return {k: v for k, v in reply.model_dump().items() if k != "intent"}


# --- the deterministic reader ---------------------------------------------------------------

_OCR_FIX = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b"})
_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*|\d+)(?:\s?\.\s?(\d{2}))?")
_LABELED_TOTAL = re.compile(
    r"(?:total\s*due|amount\s*due|balance\s*due|total|amount)\s*[:\-]?\s*" + _MONEY.pattern,
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\b([A-Z]{2,4}\d{0,2}-\s?\d{3,6})\b")
_PO = re.compile(r"\bP\s?[O0]\b[\s#:.-]*(?:P\s?[O0]-)?(\d{3,5})\b", re.IGNORECASE)
_PO_ID = re.compile(r"\bPO-(\d{3,5})\b")
_ROUTING = re.compile(r"routing[^\d]{0,12}(\d{9})", re.IGNORECASE)
_ACCOUNT = re.compile(r"account[^\d]{0,12}(\d{6,12})", re.IGNORECASE)
_PHONE = re.compile(r"\b(\d{3}-\d{3}-\d{4})\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_CONTACT_NAME = re.compile(r"(?:lead|contact|manager),?\s+([A-Z][a-z]+ [A-Z][a-z]+)")
_DUE = re.compile(r"\b(?:net|due in)\s+(\d{1,3})\b", re.IGNORECASE)

# Words that place the work in an expense account. Longer, more specific phrases first; the
# vendor's default account breaks ties.
GL_WORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "5800",
        (
            "capital improvement",
            "capital project",
            "installation of a new",
            "new water heater",
            "renovation",
        ),
    ),
    ("5600", ("insurance premium",)),
    ("5700", ("legal services", "professional fees", "lease review", "consultation")),
    ("5900", ("software", "subscription", "it support", "licenses")),
    ("5950", ("waste removal", "recycling")),
    ("5400", ("security patrol", "access control", "monitoring")),
    ("5500", ("janitorial", "cleaning crew", "cleaning")),
    ("5300", ("landscape", "irrigation", "grounds")),
    ("5200", ("utility service", "water and sewer", "billing period")),
    ("5100", ("repair", "leak", "service call", "replace", "fix", "broken")),
]


def _normalize(text: str) -> str:
    """Undo the OCR look-alikes inside words (never inside numbers) and squash spacing."""
    out = []
    for token in text.split():
        letters = sum(c.isalpha() for c in token)
        digits = sum(c.isdigit() for c in token)
        if letters and digits and letters >= digits and "-" not in token and "$" not in token:
            token = token.translate(_OCR_FIX)
        out.append(token)
    return " ".join(out).lower()


def classify(ev: ChannelEvent) -> Intent:
    text = _normalize(f"{ev.subject}\n{ev.body}")
    if "credit memo" in text or "credit note" in text:
        return "credit_memo"
    if ("routing" in text and "account" in text) or "remittance details" in text:
        return "vendor_bank_change"
    if any(w in text for w in ("new ar lead", "new accounts contact", "new contact", "has left")):
        return "vendor_contact_change"
    if any(
        w in text
        for w in (
            "haven't been paid",
            "have not been paid",
            "not received payment",
            "payment status",
        )
    ):
        return "payment_inquiry"
    if any(w in text for w in ("invoice", "amount due", "total due", "inv0ice")):
        return "invoice"
    return "other"


def extract_deterministic(ev: ChannelEvent, state: State, profile: Profile) -> Extraction:
    intent = classify(ev)
    raw = f"{ev.subject}\n{ev.body}"
    text = _normalize(raw)
    vendor = _vendor(ev.sender, text, state)
    fields: dict[str, Any] = {
        "intent": intent,
        "vendor": vendor,
        "due_in_days": _due(raw),
    }
    if intent in ("invoice", "credit_memo"):
        number = _number(raw)
        fields |= {
            "number": number,
            "amount": _amount(raw),
            "po": _po(raw, state, vendor),
            "dimension": _dimension(text, profile),
            "gl_account": _gl(text, state, vendor),
        }
        if intent == "credit_memo":
            fields["supersedes"] = _supersedes(raw, number, state, vendor)
    elif intent == "vendor_bank_change":
        r, a = _ROUTING.search(raw), _ACCOUNT.search(raw)
        fields |= {"routing": r.group(1) if r else None, "account": a.group(1) if a else None}
    elif intent == "vendor_contact_change":
        phone, email, name = (
            _PHONE.search(ev.body),
            _EMAIL.search(ev.body),
            _CONTACT_NAME.search(ev.body),
        )
        fields |= {
            "contact_phone": phone.group(1) if phone else None,
            "contact_email": email.group(0) if email else None,
            "contact_name": name.group(1) if name else None,
        }
    return Extraction(**fields)


def _vendor(sender: str, text: str, state: State) -> str | None:
    domain = sender.rpartition("@")[2].lower()
    for v in state.vendors.values():
        if domain and domain == v.domain.lower():
            return v.id
    mentioned = [v for v in state.vendors.values() if v.name.lower() in text]
    if mentioned:
        return max(mentioned, key=lambda v: len(v.name)).id
    for v in state.vendors.values():  # the domain in the body or the OCR'd header
        if v.domain.lower() in text:
            return v.id
    return None


def _number(raw: str) -> str | None:
    found = [m.group(1).replace(" ", "") for m in _NUMBER.finditer(raw)]
    found = [n for n in found if not n.startswith("PO-")]
    if not found:
        return None
    labeled = re.search(
        r"inv[o0]ice\s*(?:no|number|#|n[o0]\.?)?[:.\s]*([A-Z]{2,4}\d{0,2}-\s?\d{3,6})",
        raw,
        re.IGNORECASE,
    )
    return labeled.group(1).replace(" ", "") if labeled else found[0]


def _cents(whole: str, frac: str | None) -> int:
    return int(whole.replace(",", "")) * 100 + int(frac or 0)


def _amount(raw: str) -> int | None:
    labeled = [_cents(m.group(1), m.group(2)) for m in _LABELED_TOTAL.finditer(raw)]
    if labeled:
        return labeled[-1]
    every = [_cents(m.group(1), m.group(2)) for m in _MONEY.finditer(raw)]
    return max(every) if every else None


def _po(raw: str, state: State, vendor: str | None) -> str | None:
    ids = [f"PO-{int(m.group(1)):04d}" for m in _PO_ID.finditer(raw)]
    ids += [f"PO-{int(m.group(1)):04d}" for m in _PO.finditer(raw)]
    for pid in ids:
        po = state.purchase_orders.get(pid)
        if po is not None and (vendor is None or po.vendor == vendor):
            return pid
    return None


def _dimension(text: str, profile: Profile) -> str | None:
    named = [p for p in profile.properties if p.name.lower() in text]
    if named:
        return max(named, key=lambda p: len(p.name)).id
    m = re.search(r"\b(p-\d{2})\b", text)
    if m:
        return m.group(1).upper()
    # OCR may have mangled the name: take what follows a "property" label, find the closest
    labeled = re.search(r"property\s*[:\-]\s*([a-z0-9 ]{4,40})", text)
    if labeled:
        words = labeled.group(1).split()

        def closeness(p) -> float:  # compare against as many words as the name has
            guess = " ".join(words[: len(p.name.split())])
            return difflib.SequenceMatcher(None, p.name.lower(), guess).ratio()

        best = max(profile.properties, key=closeness)
        if closeness(best) >= 0.75:
            return best.id
    return None


def _gl(text: str, state: State, vendor: str | None) -> str | None:
    """Code the work described, not the vendor's name: a janitorial company replacing broken
    fixtures is doing repairs."""
    default = state.vendors[vendor].gl_account if vendor else None
    if vendor:
        v = state.vendors[vendor]
        text = text.replace(v.name.lower(), " ").replace(v.domain.lower(), " ")
    expenses = {a.id for a in state.ledger_accounts.values() if a.kind == "expense"}
    for gl, words in GL_WORDS:
        if gl in expenses and any(w in text for w in words):
            return gl
    return default


def _supersedes(raw: str, own: str | None, state: State, vendor: str | None) -> str | None:
    for n in (m.group(1).replace(" ", "") for m in _NUMBER.finditer(raw)):
        if n == own:
            continue
        for inv in state.invoices.values():
            if inv.number == n and (vendor is None or inv.vendor == vendor):
                return inv.id
    return None


def _due(raw: str) -> int:
    m = _DUE.search(raw)
    return int(m.group(1)) if m else 5
