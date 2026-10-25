"""O1: the LLM Operator, the only Operator the sandbox builds.

It runs the company through the reference logic it extends (operations, treasury, cash
application, recovery, approvals: O0, O2, O3), with one addition: a message that arrives with no
structured fields is read by intake (operator/intake.py: Claude through vandal/llm.py, with a
deterministic reader behind it) rather than taken from `meta`. Messages that do carry structured
fields take the reference path, and search and verification clones keep intake on the
deterministic reader, so their money outcomes never depend on a model (IMPLEMENTATION §0).

Every action intake proposes is a tool call through Blue; intake never moves money itself.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from vandal.contracts.events import ChannelEvent
from vandal.contracts.interfaces import Tools
from vandal.operator.intake import Extraction, extract
from vandal.operator.reference import ReferenceOperator, RetryPolicy
from vandal.twin.flows import CaseOpen, InvoiceArgs
from vandal.twin.profile import Profile
from vandal.twin.state import State

INBOUND_CHANNELS = ("email", "portal", "agent_msg")


class LLMOperator(ReferenceOperator):
    def __init__(
        self, profile: Profile, retry: RetryPolicy = "no_key", *, use_llm: bool = True
    ) -> None:
        super().__init__(profile, retry)
        self.profile = profile
        self.use_llm = use_llm
        self.read: list[tuple[str, Extraction]] = []  # (message id, what intake read), for the UI

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None:
        if ev.channel in INBOUND_CHANNELS and not ev.meta.get("intent") and ev.body:
            self._intake_message(ev, tools)
        else:
            super().on_event(ev, tools)

    def extract(self, ev: ChannelEvent, state: State) -> Extraction:
        return extract(ev, state, self.profile, use_llm=self.use_llm)

    def _intake_message(self, ev: ChannelEvent, tools: Tools) -> None:
        x = self.extract(ev, tools.view)
        self.read.append((ev.id, x))
        match x.intent:
            case "invoice" | "credit_memo":
                if x.vendor and x.number and x.amount:
                    tools.call(
                        self.actor,
                        "invoices.receive",
                        InvoiceArgs(
                            vendor=x.vendor,
                            number=x.number,
                            amount=x.amount,
                            dimension=x.dimension or "P-01",
                            due_in_days=x.due_in_days,
                            kind=x.intent,
                            supersedes=x.supersedes,
                            po=x.po,
                            gl_account=x.gl_account,
                            message=ev.id,
                        ),
                    )
            case "vendor_bank_change" if x.vendor and x.routing and x.account:
                meta = {
                    "intent": "vendor_bank_change",
                    "vendor": x.vendor,
                    "routing": x.routing,
                    "account": x.account,
                }
                self._change_request(ev.model_copy(update={"meta": meta}), tools)
            case "vendor_bank_change" if x.vendor:
                # A partial handoff (DESIGN 5.6): a bank change with no account number in it.
                # Nothing is applied and no request is raised; a case records why, so a person
                # can ask the vendor for the details through a verified channel.
                missing = [f for f in ("routing", "account") if getattr(x, f) is None]
                tools.call(
                    self.actor,
                    "cases.open",
                    CaseOpen(
                        subject=ev.id,
                        kind="exception",
                        reason=(
                            f"bank change request from {x.vendor} without "
                            f"{' and '.join(missing)} number; nothing applied, "
                            "details to be requested through a verified channel"
                        ),
                    ),
                )
            case "vendor_contact_change" if x.vendor:
                meta = {
                    "intent": "vendor_contact_change",
                    "vendor": x.vendor,
                    "contact_name": x.contact_name or "",
                    "contact_email": x.contact_email or "",
                    "contact_phone": x.contact_phone or "",
                }
                self._change_request(ev.model_copy(update={"meta": meta}), tools)
            case "payment_inquiry" if x.vendor:
                meta = {"intent": "payment_inquiry", "vendor": x.vendor}
                self._on_inquiry(ev.model_copy(update={"meta": meta}), tools)
            case _:
                pass  # nothing actionable: no tool call, nothing moves


def extractor(
    profile: Profile, *, use_llm: bool = True
) -> Callable[[ChannelEvent, State], Mapping[str, Any]]:
    """Intake as the scorecard scores it (verify/messy.Extractor): message and state in, the
    extracted fields out."""

    def run(ev: ChannelEvent, state: State) -> Mapping[str, Any]:
        return extract(ev, state, profile, use_llm=use_llm).model_dump()

    return run
