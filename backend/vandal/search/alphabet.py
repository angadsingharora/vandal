"""R4: the move alphabet (DESIGN 8.1), with discretized parameters, filtered by attacker
capabilities.

A scenario fixes the search window: how many days the World runs, which insertion points (`at`,
a World step index) moves may use, and which move families are in play. Parameters are
discretized into equivalence classes, so the alphabet stays small without hand-picking the
answer:

  vendor   one representative per class of exposure in the window: the vendor with the largest
           open invoice over the approval threshold, and the one with the largest open invoice
           under it. A vendor with nothing open can't be paid in the window, so it adds no class.
  fields   bank details, or the contact on file (a contact swap is how an attacker gets the
           callback number)
  sender   every sender the attacker profile allows: they differ in facts the gate can see
           (a lookalike domain vs the vendor's real one)
  channel  one representative unauthenticated channel (no fact or template tells email and
           agent messages apart), plus the portal if the attacker can take it over: a portal
           submission is authenticated evidence on its own
  confirm  inbound confirmations on every channel the attacker can fake (phone_in with caller-ID
           spoofing, video with voice cloning)
  fault    one per bank fault class (Scenario B), plus the Operator's retry timer firing
  money in the tenant with the most rent open (Scenario F); an overpayment by the attacker
           (cleared or provisional) or by the tenant, and a refund request to a new account or
           back to where the money came from

Nothing here knows which move wins. The search finds that.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vandal.contracts.moves import Move, MoveKind
from vandal.twin.profile import Profile
from vandal.twin.state import State
from vandal.twin.world import DAY_STEPS


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    days: int
    window_days: int  # moves insert anywhere in the first `window_days` days
    kinds: tuple[MoveKind, ...]

    @property
    def window(self) -> range:
        return range(self.window_days * len(DAY_STEPS))


SCENARIOS: dict[str, Scenario] = {
    "a": Scenario(
        name="a",
        description="Identity attacks on money out: vendor-master changes around the payment run",
        days=2,
        window_days=1,
        kinds=("change_request", "inbound_confirmation", "trigger_batch"),
    ),
    "b": Scenario(
        name="b",
        description="Bank faults around the payment run: timeouts, lost acks, delays, retries",
        days=2,
        window_days=1,
        kinds=("fault", "retry"),
    ),
    "f": Scenario(
        name="f",
        description="Money in: overpayments and refund requests to other accounts",
        days=2,
        window_days=1,
        kinds=("deposit", "refund_request"),
    ),
}

# Every threat family in one window, so search isn't told where to look. Kept out of SCENARIOS:
# Red's planner, held-out variants, and CEGIS pick a single family (see family_of).
ALL = Scenario(
    name="all",
    description="Every threat family at once: identity attacks, bank faults, and money in",
    days=max(s.days for s in SCENARIOS.values()),
    window_days=max(s.window_days for s in SCENARIOS.values()),
    kinds=tuple(dict.fromkeys(k for s in SCENARIOS.values() for k in s.kinds)),
)

SEARCH_SCENARIOS: dict[str, Scenario] = {**SCENARIOS, ALL.name: ALL}


def family_of(moves: Sequence[Move]) -> str:
    """The single threat family whose window covers every move, or "all" for a mixed attack
    (one that crosses families, which only the combined search can find)."""
    kinds = {m.kind for m in moves}
    for name, s in SCENARIOS.items():
        if kinds and kinds <= set(s.kinds):
            return name
    return ALL.name


# One move per fault class (twin/bank.py). A one-day delay stands for every delay: longer
# ones only push settlement further past the window.
FAULTS: tuple[dict[str, str | int], ...] = (
    {"kind": "timeout"},
    {"kind": "drop_ack"},
    {"kind": "duplicate_ack"},
    {"kind": "delay", "days": 1},
    {"kind": "feed_delay", "days": 1},
)


def vendor_classes(state: State, profile: Profile) -> list[str]:
    """One vendor per exposure class (see module docstring), in a stable order."""
    threshold = profile.approval_matrix.threshold
    open_by_vendor: dict[str, int] = {}
    for inv in state.invoices.values():
        if inv.status in ("received", "validated", "approved", "scheduled"):
            open_by_vendor[inv.vendor] = max(open_by_vendor.get(inv.vendor, 0), inv.amount)

    def largest(pred) -> str | None:
        ranked = sorted(((a, v) for v, a in open_by_vendor.items() if pred(a)), reverse=True)
        return ranked[0][1] if ranked else None

    reps = [largest(lambda a: a > threshold), largest(lambda a: a <= threshold)]
    return [v for v in reps if v is not None]


def confirmation_channels(profile: Profile) -> list[str]:
    caps = profile.attacker_capabilities
    return [
        ch for ch, able in (("phone_in", caps.spoof_caller_id), ("video", caps.clone_voice)) if able
    ]


def build_alphabet(scenario: Scenario, state: State, profile: Profile) -> list[Move]:
    caps = profile.attacker_capabilities
    vendors = vendor_classes(state, profile)
    unauthenticated = [c for c in caps.change_request_channels if c != "portal"]
    channels = unauthenticated[:1] + (
        ["portal"] if "portal" in caps.change_request_channels else []
    )
    moves: list[Move] = []
    for at in scenario.window:
        if "change_request" in scenario.kinds:
            for vendor in vendors:
                for fields in ("bank", "contact"):
                    for channel in channels:
                        for sender in caps.senders:
                            moves.append(
                                Move(
                                    kind="change_request",
                                    at=at,
                                    params={
                                        "vendor": vendor,
                                        "fields": fields,
                                        "channel": channel,
                                        "sender": sender,
                                    },
                                )
                            )
        if "inbound_confirmation" in scenario.kinds:
            for vendor in vendors:
                for ch in confirmation_channels(profile):
                    moves.append(
                        Move(
                            kind="inbound_confirmation",
                            at=at,
                            params={
                                "vendor": vendor,
                                "channel": ch,
                                "voice_match": 95,
                            },
                        )
                    )
        if "trigger_batch" in scenario.kinds:
            moves.append(Move(kind="trigger_batch", at=at, params={}))
        if "fault" in scenario.kinds:
            moves += [Move(kind="fault", at=at, params=dict(f)) for f in FAULTS]
        if "retry" in scenario.kinds:
            moves.append(Move(kind="retry", at=at, params={}))
        for customer in customer_classes(state) if "deposit" in scenario.kinds else ():
            overpay = {"customer": customer, "amount": "overpay"}
            moves += [
                Move(kind="deposit", at=at, params={**overpay, "party": "attacker", "cleared": 0}),
                Move(kind="deposit", at=at, params={**overpay, "party": "attacker"}),
                Move(kind="deposit", at=at, params=overpay),
            ]
            moves += [
                Move(
                    kind="refund_request",
                    at=at,
                    params={"customer": customer, "party": "attacker", "dest": dest},
                )
                for dest in ("new", "source")
            ]
    return moves


def customer_classes(state: State) -> list[str]:
    """The tenant with the most rent open: refunds don't depend on which tenant it is."""
    owed: dict[str, int] = {}
    for inv in state.customer_invoices.values():
        owed[inv.customer] = owed.get(inv.customer, 0) + inv.amount - inv.paid
    return [max(sorted(owed), key=owed.__getitem__)] if owed else []


def touches(move: Move) -> str:
    """The entity a move reads or writes, for partial-order reduction. Moves that drive the
    Operator (a batch run) touch everything."""
    if move.kind in ("change_request", "inbound_confirmation", "submit_invoice"):
        return f"vendor:{move.params['vendor']}"
    if move.kind in ("deposit", "refund_request"):
        return f"customer:{move.params['customer']}"
    return "*"


def independent(a: Move, b: Move) -> bool:
    ta, tb = touches(a), touches(b)
    return ta != "*" and tb != "*" and ta != tb
