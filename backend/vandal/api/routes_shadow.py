"""Shadow mode: a company's real accounts-payable activity, replayed through Guard on a clone of
the books. Report only.

The gap between "measured on the twin" and "on your real systems" closes here. A finance team
exports what their AP agent (or their people) did last month: bills received, payments made,
vendor bank and contact changes, callbacks placed. Each row becomes the tool call the Operator
would have made, in order, on a fresh clone of the run's company under the run's policy. Guard
rules on every call as it would in the live path, and the report says, row by row, what it
would have allowed, held, escalated or blocked, and why. The live run is untouched.

Rows come as JSON, or as CSV with a header (kind, vendor, number, amount, po, po_amount,
received, channel, sender, routing, account, contact_name, contact_email, contact_phone, method,
ref). Vendors match by id, name or domain against the run's vendor master; a vendor not on file
is reported as unmatched rather than guessed. A bill that had a purchase order names it in `po`
(and its amount in `po_amount` when it differs from the bill; `received=no` when the goods never
arrived): the PO and receipt are seeded on the clone so the three-way match has something to
match, as the company's own books would. Every row runs on day 0 of the clone: the report is
about what Guard says to each action, not about the calendar.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from vandal.api import deps
from vandal.api.registry import RunHandle
from vandal.api.routes_guard import _say
from vandal.contracts.controls import DECISION_ORDER
from vandal.contracts.entities import Actor, PurchaseOrder, Receipt, Vendor
from vandal.sandbox import Sandbox, new_sandbox
from vandal.twin.flows import (
    TOOLS,
    CallbackArgs,
    ChangeRef,
    ChangeRequestArgs,
    DecideArgs,
    InvoiceArgs,
    InvoiceRef,
    PaymentRef,
    ScheduleArgs,
)
from vandal.twin.world import settle

router = APIRouter()

MAX_ROWS = 500
OPERATOR = Actor(id="OP-1", role="operator")

Kind = Literal["bill", "payment", "vendor_bank_change", "vendor_contact_change", "callback"]
KINDS: tuple[str, ...] = Kind.__args__  # type: ignore[attr-defined]

COLUMNS = [
    "kind",
    "vendor",
    "number",
    "amount",
    "po",
    "po_amount",
    "received",
    "channel",
    "sender",
    "routing",
    "account",
    "contact_name",
    "contact_email",
    "contact_phone",
    "method",
    "ref",
]


class Row(BaseModel):
    """One thing that happened in accounts payable. Which fields matter depends on `kind`:
    a bill has a vendor, number and amount; a payment names the bill's number; a change has
    the vendor, the channel it came in on, who sent it, and the new details; a callback names
    the vendor and how it was verified (phone_outbound or portal)."""

    model_config = ConfigDict(extra="ignore")

    kind: Kind
    vendor: str | None = Field(default=None, max_length=120)
    number: str | None = Field(default=None, max_length=60)
    amount: float | None = Field(default=None, ge=0)  # dollars
    po: str | None = Field(default=None, max_length=60)  # the bill's purchase order, if any
    po_amount: float | None = Field(default=None, ge=0)  # dollars; the bill's amount when blank
    received: str | None = Field(default=None, max_length=10)  # "no": goods never arrived
    channel: str | None = Field(default=None, max_length=30)
    sender: str | None = Field(default=None, max_length=120)
    routing: str | None = Field(default=None, max_length=30)
    account: str | None = Field(default=None, max_length=40)
    contact_name: str | None = Field(default=None, max_length=80)
    contact_email: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=40)
    method: str | None = Field(default=None, max_length=30)
    ref: str | None = Field(default=None, max_length=60)


class ShadowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[Row] | None = Field(default=None, max_length=MAX_ROWS)
    csv: str | None = Field(default=None, max_length=400_000)
    # Over-threshold payments wait for a human; in shadow the human is assumed to have approved,
    # as they did in reality, so the chain reaches execution and Guard's execute-time checks.
    approve_escalations: bool = True


def rows_from_csv(text: str) -> list[Row]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "kind" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(
            400, f"the CSV needs a header with at least 'kind'; columns: {', '.join(COLUMNS)}"
        )
    rows: list[Row] = []
    for n, raw in enumerate(reader, start=2):
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(clean.values()):
            continue
        kind = clean.get("kind", "").lower().replace(" ", "_").replace("-", "_")
        if kind not in KINDS:
            raise HTTPException(
                400, f"line {n}: unknown kind {clean.get('kind')!r}; one of {', '.join(KINDS)}"
            )
        data: dict[str, Any] = {k: v for k, v in clean.items() if k in COLUMNS and v}
        data["kind"] = kind
        for money in ("amount", "po_amount"):
            if money in data:
                try:
                    data[money] = float(str(data[money]).replace("$", "").replace(",", ""))
                except ValueError:
                    raise HTTPException(
                        400, f"line {n}: {money} {data[money]!r} is not a number"
                    ) from None
        try:
            rows.append(Row.model_validate(data))
        except ValueError as err:
            raise HTTPException(400, f"line {n}: {err}") from None
        if len(rows) > MAX_ROWS:
            raise HTTPException(400, f"at most {MAX_ROWS} rows")
    return rows


def usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _worst(decisions: list[str]) -> str:
    return max(decisions, key=DECISION_ORDER.__getitem__, default="allow")


class Shadow:
    """Replays rows on one clone and keeps the report."""

    def __init__(self, handle: RunHandle, approve_escalations: bool) -> None:
        self.sb: Sandbox = new_sandbox(
            handle.sandbox.profile, seed=handle.seed, policy=handle.policy, use_llm=False
        )
        self.approve_escalations = approve_escalations
        self.bills: dict[str, str] = {}  # bill number -> invoice id on the clone
        self.dimension = handle.sandbox.profile.properties[0].id
        self.approvers = handle.sandbox.profile.approval_matrix.approvers
        self.steps: list[dict[str, Any]] = []

    @property
    def state(self):
        return self.sb.run.state

    # --- one tool call, recorded ------------------------------------------------------------

    def call(self, tool: str, args: BaseModel, actor: Actor = OPERATOR) -> dict[str, Any]:
        result = self.sb.tools.call(actor, tool, args)
        verdict = result.verdict.model_dump(mode="json")
        facts = verdict.get("facts", {})
        step = {
            "tool": tool,
            "stage": TOOLS[tool].stage,
            "actor": actor.id,
            "decision": verdict["decision"],
            "fired": verdict["fired"],
            "requires": facts.get("gate.requires", []),
            "cites": verdict["cites"],
            "ok": result.ok,
            "error": result.data.get("error"),
            "summary": _say(verdict, tool),
        }
        self.steps.append(step)
        return step

    # --- matching ----------------------------------------------------------------------------

    def vendor(self, text: str | None) -> Vendor | None:
        if not text:
            return None
        key = text.strip().lower()
        for v in self.state.vendors.values():
            if key in (v.id.lower(), v.name.lower(), v.domain.lower()):
                return v
        return None

    def invoice_for(self, number: str | None) -> str | None:
        if not number:
            return None
        if number in self.bills:
            return self.bills[number]
        key = number.strip().lower()
        for inv in self.state.invoices.values():
            if inv.number.lower() == key:
                return inv.id
        return None

    # --- the kinds ---------------------------------------------------------------------------

    def bill(self, row: Row) -> tuple[dict[str, Any], str | None]:
        v = self.vendor(row.vendor)
        if v is None:
            return {}, f"vendor {row.vendor!r} is not in the vendor master"
        if not row.number or row.amount is None:
            return {}, "a bill needs a number and an amount"
        cents = int(round(row.amount * 100))
        po_id = self.seed_po(v, row, cents)
        args = InvoiceArgs(
            vendor=v.id,
            number=row.number,
            amount=cents,
            dimension=self.dimension,
            po=po_id,
        )
        step = self.call("invoices.receive", args)
        if step["ok"]:
            inv = next((i for i in self.state.invoices.values() if i.number == row.number), None)
            if inv is not None:
                self.bills[row.number] = inv.id
        return {"vendor": v.id, "vendor_name": v.name}, None

    def seed_po(self, v: Vendor, row: Row, cents: int) -> str | None:
        """The purchase order (and receipt) a bill row says it had, put on the clone's books the
        way the generator puts the company's own there: this is the company's record, not an
        action Guard rules on."""
        if not row.po:
            return None
        state = self.state
        po_id = f"PO-S{len(state.purchase_orders) + 1:04d}"
        po_cents = int(round(row.po_amount * 100)) if row.po_amount is not None else cents
        state.purchase_orders[po_id] = PurchaseOrder(
            id=po_id, vendor=v.id, amount=po_cents, dimension=self.dimension, issued_on=state.day
        )
        if (row.received or "yes").strip().lower() not in ("no", "n", "false", "0"):
            rc_id = f"RC-S{len(state.receipts) + 1:04d}"
            state.receipts[rc_id] = Receipt(
                id=rc_id, po=po_id, amount=po_cents, received_on=state.day
            )
        return po_id

    def payment(self, row: Row) -> tuple[dict[str, Any], str | None]:
        iid = self.invoice_for(row.number)
        if iid is None:
            return {}, f"no bill numbered {row.number!r} in this file or on the books"
        inv = self.state.invoices[iid]
        info = {
            "invoice": iid,
            "vendor": inv.vendor,
            "vendor_name": self.state.vendors[inv.vendor].name,
            "amount_cents": inv.amount,
        }
        ref = InvoiceRef(invoice=iid)
        if inv.status == "received":
            self.call("invoices.validate", ref)
        if self.state.invoices[iid].status == "validated":
            step = self.call("approvals.request", ref)
            if step["decision"] == "escalate" and self.approve_escalations:
                req = next(
                    (
                        r
                        for r in self.state.approval_requests.values()
                        if r.subject == iid and r.status == "pending"
                    ),
                    None,
                )
                if req is not None:
                    amount = req.instruction.amount
                    approver = next(
                        a for a in self.approvers if a.max_amount is None or amount <= a.max_amount
                    )
                    self.call(
                        "approvals.decide",
                        DecideArgs(
                            request=req.id, approve=True, reason="shadow: approved in reality"
                        ),
                        Actor(id=approver.id, role="approver"),
                    )
        if self.state.invoices[iid].status == "approved":
            self.call("payments.schedule", ScheduleArgs(invoice=iid, pay_on=self.state.day))
        if self.state.invoices[iid].status == "scheduled":
            self.call("payments.execute", ref)
        pay = next(
            (
                p
                for p in self.state.payments.values()
                if self.state.payment_instructions[p.instruction].invoice == iid
                and p.status == "scheduled"
            ),
            None,
        )
        if pay is not None:
            step = self.call("payments.submit", PaymentRef(payment=pay.id))
            if step["decision"] == "hold" and any(f.endswith(".key") for f in step["fired"]):
                self.call(
                    "payments.submit", PaymentRef(payment=pay.id, idempotency_key=pay.instruction)
                )
            instr = self.state.payment_instructions[pay.instruction]
            acct = self.state.vendor_bank_accounts.get(instr.payee_account)
            info |= {
                "payment": pay.id,
                "paid": self.state.payments[pay.id].status not in ("failed", "scheduled"),
                "payee_account": instr.payee_account,
                "payee_status": acct.status if acct else None,
                "payee_source": acct.source if acct else None,
            }
        return info, None

    def change(
        self, row: Row, fields: Literal["bank", "contact"]
    ) -> tuple[dict[str, Any], str | None]:
        v = self.vendor(row.vendor)
        if v is None:
            return {}, f"vendor {row.vendor!r} is not in the vendor master"
        channel = (row.channel or "email").lower()
        sender = row.sender or f"ap@{v.domain}"
        args = ChangeRequestArgs(
            vendor=v.id,
            fields=fields,
            channel=channel,
            sender=sender,
            routing=row.routing if fields == "bank" else None,
            account=row.account if fields == "bank" else None,
            contact_name=row.contact_name if fields == "contact" else None,
            contact_email=row.contact_email if fields == "contact" else None,
            contact_phone=row.contact_phone if fields == "contact" else None,
        )
        self.call("vendors.change_request", args)
        return {"vendor": v.id, "vendor_name": v.name}, None

    def callback(self, row: Row) -> tuple[dict[str, Any], str | None]:
        v = self.vendor(row.vendor)
        if v is None:
            return {}, f"vendor {row.vendor!r} is not in the vendor master"
        held = [
            c
            for c in self.state.change_requests.values()
            if c.vendor == v.id and c.status == "held"
        ]
        if not held:
            return {
                "vendor": v.id,
                "vendor_name": v.name,
            }, f"nothing is held for {v.name}; a callback verifies a held change"
        cr = held[-1]
        method = (row.method or "phone_outbound").strip().lower()
        if method == "portal":
            self.call("evidence.record_portal", ChangeRef(change=cr.id))
        else:
            step = self.call(
                "evidence.request_callback",
                CallbackArgs(change=cr.id, contact_as_of="before_request", window_days=30),
            )
            if step["ok"]:
                # the vendor answers, the Operator hears it and applies the change
                settle(self.sb.run, self.sb.tools, self.sb.operator, None)
        if self.state.change_requests[cr.id].status == "held":
            self.call("vendors.apply_change", ChangeRef(change=cr.id))
        return {
            "vendor": v.id,
            "vendor_name": v.name,
            "change": cr.id,
            "change_status": self.state.change_requests[cr.id].status,
        }, None

    def run(self, rows: list[Row]) -> list[dict[str, Any]]:
        out = []
        for n, row in enumerate(rows, start=1):
            self.steps = []
            try:
                match row.kind:
                    case "bill":
                        info, note = self.bill(row)
                    case "payment":
                        info, note = self.payment(row)
                    case "vendor_bank_change":
                        info, note = self.change(row, "bank")
                    case "vendor_contact_change":
                        info, note = self.change(row, "contact")
                    case "callback":
                        info, note = self.callback(row)
            except (KeyError, ValueError, TypeError) as err:  # a row the twin can't take
                info, note = {}, f"{type(err).__name__}: {err}"
            decision = (
                "unmatched"
                if note and not self.steps
                else _worst([s["decision"] for s in self.steps])
            )
            out.append(
                {
                    "n": n,
                    "ref": row.ref,
                    "kind": row.kind,
                    "input": row.model_dump(exclude_none=True, exclude={"ref", "kind"}),
                    **info,
                    "decision": decision,
                    "note": note,
                    "steps": self.steps,
                }
            )
        return out


def summarize(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    by: dict[str, int] = {"allow": 0, "escalate": 0, "hold": 0, "block": 0, "unmatched": 0}
    money_stopped = 0
    money_through = 0
    money_unverified = 0  # paid to an account nothing ever verified
    attention = []
    for r in rows:
        by[r["decision"]] = by.get(r["decision"], 0) + 1
        if r["kind"] == "payment":
            amt = r.get("amount_cents", 0)
            if r.get("paid"):
                money_through += amt
                if r.get("payee_status") != "verified":
                    money_unverified += amt
                    attention.append(
                        {
                            "n": r["n"],
                            "ref": r.get("ref"),
                            "kind": r["kind"],
                            "vendor_name": r.get("vendor_name"),
                            "decision": "paid_unverified",
                            "summary": (
                                f"{usd(amt)} went to {r['payee_account']}, an account that was "
                                f"{r.get('payee_status') or 'not on file'} "
                                f"({r.get('payee_source')})."
                            ),
                            "requires": [],
                        }
                    )
            elif r["decision"] in ("hold", "block"):
                money_stopped += amt
        # an escalation is a human looking, which is the point; holds and blocks need a look
        if r["decision"] in ("hold", "block"):
            why = next((s for s in r["steps"] if s["decision"] == r["decision"]), None)
            attention.append(
                {
                    "n": r["n"],
                    "ref": r.get("ref"),
                    "kind": r["kind"],
                    "vendor_name": r.get("vendor_name"),
                    "decision": r["decision"],
                    "summary": why["summary"] if why else "",
                    "requires": why["requires"] if why else [],
                }
            )
    return {
        "policy": policy,
        "rows": len(rows),
        "by_decision": by,
        "money_stopped": money_stopped,
        "money_through": money_through,
        "money_unverified": money_unverified,
        "attention": attention,
    }


@router.get("/shadow/columns")
def shadow_columns() -> dict[str, Any]:
    """The CSV header shadow mode reads, and what each kind of row needs."""
    return {
        "columns": COLUMNS,
        "kinds": {
            "bill": (
                "vendor, number, amount (dollars); po (its purchase order number, if it had "
                "one), po_amount (dollars, when it differs), received (no: goods never arrived)"
            ),
            "payment": "number (of a bill in this file, or on the books)",
            "vendor_bank_change": (
                "vendor, channel (email | portal | agent_msg), sender (email address), "
                "routing, account"
            ),
            "vendor_contact_change": (
                "vendor, channel, sender, contact_name, contact_email, contact_phone"
            ),
            "callback": (
                "vendor, method (phone_outbound | portal): verifies the vendor's latest held change"
            ),
        },
        "max_rows": MAX_ROWS,
    }


@router.post("/runs/{run_id}/shadow")
def shadow(request: Request, run_id: str, body: ShadowBody) -> dict[str, Any]:
    """Replay the rows through Guard on a fresh clone of this run's company and policy. The
    live run is untouched; the report says what Guard would have done to each row."""
    handle = deps.get_run(request, run_id)
    if body.csv is not None and body.rows:
        raise HTTPException(400, "give rows or csv, not both")
    rows = body.rows if body.rows is not None else rows_from_csv(body.csv or "")
    if not rows:
        raise HTTPException(400, "no rows")
    with handle.lock:
        shadow = Shadow(handle, body.approve_escalations)
    report = shadow.run(rows)
    return {
        "run_id": run_id,
        "policy": handle.policy.version,
        "company": shadow.state.company,
        "summary": summarize(report, handle.policy.version),
        "rows": report,
    }
