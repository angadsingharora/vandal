"""O1 done-when: field and GL-coding accuracy against the oracle labels is reported by the
scorecard, 90% or better. The messy-document items (DESIGN 5.6) are the planted inputs; the LLM
Operator's intake reads them (Claude when a model is configured, the deterministic reader
otherwise), and the LLM Operator runs the company on them through Blue."""

from __future__ import annotations

from functools import partial

import pytest

from vandal.contracts.events import ChannelEvent
from vandal.operator.intake import classify, extract_deterministic
from vandal.operator.llm_operator import LLMOperator
from vandal.sandbox import intake_extractor, new_sandbox
from vandal.synth.templates import V0
from vandal.twin import ledger
from vandal.twin.world import settle
from vandal.verify.invariants import check
from vandal.verify.messy import FIELDS, FORMATS, messy_items, reopen_as_message, score
from vandal.verify.suite import verify

TARGET = 0.9


@pytest.fixture(scope="module")
def items():
    sb = new_sandbox()
    return sb, messy_items(sb.run.state, sb.profile)


def test_every_pending_invoice_is_planted_in_every_format(items) -> None:
    sb, planted = items
    pending = {i.id for i in sb.run.state.invoices.values() if i.status == "received"}
    assert {it.truth.invoice for it in planted} == pending
    assert {it.format for it in planted} == set(FORMATS)
    assert sum(it.twisted for it in planted) >= 3  # GL coding has to read the work described
    for it in planted:
        inv = sb.run.state.invoices[it.truth.invoice]
        assert (it.truth.vendor, it.truth.number, it.truth.amount) == (
            inv.vendor,
            inv.number,
            inv.amount,
        )
        assert it.message.meta == {}  # nothing structured: intake has to read the document
        assert it.truth.number in it.message.body or it.truth.number in it.message.subject


def test_items_replay_identically() -> None:
    a, b = new_sandbox(), new_sandbox()
    assert messy_items(a.run.state, a.profile) == messy_items(b.run.state, b.profile)
    other = new_sandbox(seed=11)
    assert messy_items(other.run.state, other.profile) != messy_items(a.run.state, a.profile)


def test_intake_meets_the_accuracy_target(items) -> None:
    sb, planted = items
    acc = score(planted, intake_extractor(sb.profile), sb.run.state)
    assert acc.items == len(planted) and acc.fields_total == len(planted) * len(FIELDS)
    assert acc.extraction_accuracy >= TARGET, acc.misses
    assert acc.gl_coding_accuracy >= TARGET, acc.misses
    assert set(acc.by_format) == set(FORMATS)
    assert all(v >= 0.8 for v in acc.by_format.values()), acc.by_format
    assert sum(acc.sources.values()) == acc.items


def test_gl_is_coded_from_the_work_not_the_vendor(items) -> None:
    sb, planted = items
    twisted = [it for it in planted if it.twisted]
    for it in twisted:
        x = extract_deterministic(it.message, sb.run.state, sb.profile)
        assert (
            x.gl_account == it.truth.gl_account != sb.run.state.vendors[it.truth.vendor].gl_account
        )


def test_classifier_tells_the_channel_events_apart() -> None:
    def ev(subject, body, channel="email"):
        return ChannelEvent(
            id="M", day=0, channel=channel, sender="x@y.com", subject=subject, body=body
        )

    assert classify(
        ev("Updated remittance details", "Routing: 026009593\nAccount: 1234567890")
    ) == ("vendor_bank_change")
    assert classify(
        ev("New accounts contact", "Sam has left. Our new AR lead, Jordan Reyes, ...")
    ) == ("vendor_contact_change")
    assert classify(ev("Re: remittance", "We haven't been paid for HPC-2291 yet.")) == (
        "payment_inquiry"
    )
    assert (
        classify(ev("Credit memo CM-1", "Credit memo correcting invoice HPC-2291")) == "credit_memo"
    )
    assert classify(ev("Lunch?", "Are you free Thursday?")) == "other"


def test_llm_operator_receives_a_messy_invoice_through_blue(items) -> None:
    """Drop the structured copy of a planted invoice and let its document arrive instead. The
    LLM Operator receives it with the right fields and GL, Blue gates the call, and the company
    pays it like any other invoice."""
    _, planted = items
    item = next(it for it in planted if it.twisted)
    sb = new_sandbox(operator="llm", policy=V0)
    reopen_as_message(sb.run.state, item)
    assert isinstance(sb.operator, LLMOperator)
    sb.operator.on_event(item.message, sb.tools)
    settle(sb.run, sb.tools, sb.operator, None)
    state = sb.run.state
    inv = next(i for i in state.invoices.values() if i.number == item.truth.number)
    t = item.truth
    assert (inv.vendor, inv.amount, inv.po, inv.dimension, inv.gl_account) == (
        t.vendor,
        t.amount,
        t.po,
        t.dimension,
        t.gl_account,
    )
    receive = [
        e
        for e in state.events
        if e.kind == "gate.verdict" and e.payload["tool"] == "invoices.receive"
    ]
    assert len(receive) == 1 and receive[0].payload["verdict"]["decision"] == "allow"
    assert sb.operator.read and sb.operator.read[-1][0] == item.message.id
    sb.operate(4)
    final = sb.run.state
    assert final.invoices[inv.id].status == "paid"
    assert check(final) == []
    posted = [
        je
        for je in final.journal
        if any(ln.account == t.gl_account for ln in je.lines) and inv.id in je.memo
    ]
    assert posted, "the approval posted the expense to the account intake coded"
    assert ledger.balance(final, t.gl_account) >= t.amount


def test_llm_operator_runs_the_company_like_the_reference() -> None:
    """Structured events take the reference path, so legitimate operations end the same way."""
    ref = new_sandbox().operate(5).run.state
    llm = new_sandbox(operator="llm").operate(5).run.state
    assert ref.entity_hash() == llm.entity_hash()
    assert check(llm) == []


def test_a_message_nobody_can_act_on_moves_nothing() -> None:
    sb = new_sandbox(operator="llm")
    before = sb.tools.calls
    sb.operator.on_event(
        ChannelEvent(
            id="M-1", day=0, channel="email", sender="a@b.com", subject="Hi", body="Lunch?"
        ),
        sb.tools,
    )
    assert sb.tools.calls == before


def test_vandal_intake_cli(capsys) -> None:
    from vandal.cli import main

    assert main(["intake", "--no-llm"]) == 0
    out = capsys.readouterr().out
    assert "extraction accuracy" in out and "GL-coding accuracy" in out and "meets" in out
    assert main(["intake", "--no-llm", "--target", "1.01"]) == 1


@pytest.mark.slow
def test_scorecard_reports_intake_accuracy() -> None:
    pack = verify(
        V0,
        V0,
        lambda p: partial(new_sandbox, "bayline", policy=p),
        profile="bayline",
        depth=1,
        intake=intake_extractor("bayline"),
    )
    after = pack.metrics["after"]
    assert after.extraction_accuracy is not None and after.extraction_accuracy >= TARGET
    assert after.gl_coding_accuracy is not None and after.gl_coding_accuracy >= TARGET
    assert any("messy-document items" in n for n in after.notes)
