"""R6: the verification evidence model, and the environment that answers callbacks.

Evidence is what clears a hold whose Check carries a `require` clause (T1). It comes from:

  inbound   the attacker (or a real vendor) calls in or joins a video call to "confirm" a change.
            Caller ID and voice can be faked, so inbound evidence is never authenticated.
  outbound  the Operator calls the vendor back on a number from the vendor master, as of the day
            the control says (`contact_as_of`). The callee answers truthfully if the number
            reaches the real vendor, and confirms falsely if it reaches the attacker.

Who answers a callback is the environment's business, not the company's: the twin only sees the
answer. The Environment is passed to the World loop and never to Tools, so neither Tools nor an
Operator can ask it the truth. The legitimate environment below answers as a world with no
attacker would (every request is genuine); the harness (verify/replay.py) supplies one that
knows which numbers and requests are the attacker's.
"""

from __future__ import annotations

from typing import Protocol

from vandal.contracts.controls import Requirement
from vandal.contracts.entities import Evidence, SimDay, VendorChangeRequest, VendorContact
from vandal.contracts.events import ChannelEvent
from vandal.twin.state import State

DEFAULT_WINDOW_DAYS = 30


def contact_as_of_day(
    request: VendorChangeRequest, as_of: str, window_days: int | None, today: SimDay
) -> SimDay:
    """`current` is today's vendor master; `before_request` is the record as it stood
    `window_days` before the request arrived, so a recent contact swap doesn't count."""
    if as_of == "current":
        return today
    return request.received_on - (window_days or DEFAULT_WINDOW_DAYS)


def contact_on(state: State, vendor: str, day: SimDay) -> VendorContact | None:
    found = [
        c
        for c in state.vendor_contacts.values()
        if c.vendor == vendor and c.valid_from <= day and (c.valid_to is None or c.valid_to > day)
    ]
    return found[-1] if found else None


def satisfying(state: State, request_id: str, req: Requirement) -> list[str]:
    """Evidence ids that clear `req` for this change request (empty if none do)."""
    request = state.change_requests.get(request_id)
    if request is None:
        return []
    window = req.window_days or DEFAULT_WINDOW_DAYS
    ok = []
    for ev in state.evidence.values():
        if ev.change_request != request_id or ev.status != "answered" or ev.confirms is not True:
            continue
        if ev.channel not in req.accepted_channels:
            continue
        if ev.received_on - request.received_on > window:
            continue
        stale_contact = ev.contact_as_of is None or ev.contact_as_of > request.received_on - window
        if (
            ev.channel == "phone_outbound"
            and req.contact_as_of == "before_request"
            and stale_contact
        ):
            continue
        ok.append(ev.id)
    return ok


# --- the environment ------------------------------------------------------------------------


class Environment(Protocol):
    def genuine(self, state: State, request: VendorChangeRequest) -> bool:
        """Did the real vendor actually ask for this change?"""
        ...

    def attacker_phone(self, phone: str) -> bool:
        """Does this number ring the attacker?"""
        ...


class LegitEnvironment:
    """A world with no attacker: every request is genuine and every number is the vendor's."""

    def genuine(self, state: State, request: VendorChangeRequest) -> bool:
        return True

    def attacker_phone(self, phone: str) -> bool:
        return False


def answer_callbacks(state: State, env: Environment) -> list[tuple[str, dict]]:
    """Answers to pending outbound callbacks, as (kind, payload) event specs. The callee confirms
    if it's the attacker, or if it's the real vendor and the request is genuine."""
    specs = []
    for ev in state.evidence.values():
        if ev.status != "pending":
            continue
        request = state.change_requests[ev.change_request]
        confirms = env.attacker_phone(ev.phone or "") or env.genuine(state, request)
        specs.append(("callback.answered", {"evidence": ev.id, "confirms": confirms}))
    return specs


def answered_notice(evidence: Evidence, day: SimDay) -> ChannelEvent:
    """What the Operator hears when a callback is answered."""
    return ChannelEvent(
        id=f"CALL-{evidence.id}",
        day=day,
        channel="system",
        sender="phone",
        subject="callback_answered",
        meta={
            "intent": "callback_answered",
            "evidence": evidence.id,
            "request": evidence.change_request,
        },
    )
