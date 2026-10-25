"""vandal seed | run | attack | search | synth | verify | inject | intake"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

# Exhaustive depth 4 takes ~75s even with partial-order reduction and 8-10 workers, so the
# default is 3 (IMPLEMENTATION R4, step 5). --depth 4 still works.
DEFAULT_DEPTH = 3

COMMANDS: dict[str, tuple[str, str]] = {
    "seed": ("Print the seeded company summary", "R1"),
    "run": ("Run legitimate operations for N business days", "R2"),
    "attack": ("Replay a hand-written adversary trace", "R3"),
    "search": ("Bounded adversarial search for violations", "R4"),
    "synth": ("Diagnose and synthesize a control (CEGIS)", "R8"),
    "verify": ("Run the verification suite against a policy", "R7"),
    "inject": ("Run a user-authored threat in plain language", "R9"),
    "rebuild": ("Rebuild a persisted run from its events and check its hash", "R12"),
    "intake": ("Score the LLM Operator's intake on the messy-document items", "O1"),
}


def cmd_seed(args: argparse.Namespace) -> int:
    from vandal.twin.profile import load_profile
    from vandal.twin.seed import seed_state, summary

    profile = load_profile(args.profile)
    print(summary(seed_state(profile, seed=args.seed), profile))
    return 0


def load_policy(name: str | None):
    from vandal.synth.templates import load_policy as load

    return load(name)


def _policy(args: argparse.Namespace):
    return load_policy(args.policy)


def _lint_policy(policy, profile) -> list[str]:
    from vandal.synth.lint import lint

    return [
        f"{f.lint}: {f.message}"
        for c in policy.controls
        for f in lint(c, profile.attacker_capabilities)
    ]


def _print_policy(policy) -> None:
    print(f"policy {policy.version}" + (f" (from {policy.parent})" if policy.parent else ""))
    for line in policy.diff:
        print(f"  {line}")


def cmd_run(args: argparse.Namespace) -> int:
    from collections import Counter

    from vandal.sandbox import new_sandbox
    from vandal.verify.invariants import check

    policy = _policy(args)
    store = writer = run_id = None
    if args.persist:
        from vandal.api.db import Store

        store = Store(args.db)
        store.migrate()
        run_id = store.create_run(
            kind="operate", profile=args.profile, policy=policy.version, seed=args.seed
        )
        writer = store.writer(run_id)
    sb = new_sandbox(
        args.profile,
        seed=args.seed,
        policy=policy,
        sink=writer,
        operator=args.operator,
        use_llm=not args.no_llm,
    )
    sb.operate(args.days)
    state = sb.run.state
    if store is not None and writer is not None and run_id is not None:
        writer.flush()
        store.finish_run(
            run_id,
            {"days": args.days, "events": len(state.events), "state_hash": state.state_hash()},
        )
    verdicts = Counter(
        e.payload["verdict"]["decision"] for e in state.events if e.kind == "gate.verdict"
    )
    statuses = Counter(i.status for i in state.invoices.values())
    pays = Counter(p.status for p in state.payments.values())
    violations = check(state)
    print(f"{state.company}: ran {args.days} business days (now day {state.day})")
    print(f"  tool calls       {sb.tools.calls}  verdicts {dict(sorted(verdicts.items()))}")
    print(f"  invoices         {dict(sorted(statuses.items()))}")
    print(f"  payments         {dict(sorted(pays.items()))}")
    for ba in state.bank_accounts.values():
        print(f"  bank {ba.name:<11} ${ba.balance / 100:,.2f}")
    print(f"  invariants       {'all hold' if not violations else ''}")
    for v in violations:
        print(f"    {v.invariant}: {v.message}")
    print(f"  events           {len(state.events)}")
    print(f"  state_hash       {state.state_hash()}")
    if run_id is not None:
        print(f"  persisted        {run_id} ({writer.written} events) in {store.dialect}")
    return 1 if violations else 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    from vandal.api.db import Store

    store = Store(args.db)
    row = store.run_row(args.run_id)
    state = store.rebuild(args.run_id)
    recorded = (row["summary"] or {}).get("state_hash")
    rebuilt = state.state_hash()
    print(
        f"run {args.run_id}: {row['kind']} on {row['profile']} (seed {row['seed']}, "
        f"policy {row['policy']}), {len(state.events)} events"
    )
    print(f"  recorded   {recorded}")
    print(f"  rebuilt    {rebuilt}")
    same = recorded == rebuilt
    print("  identical" if same else "  MISMATCH")
    return 0 if same else 1


def cmd_attack(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import new_sandbox
    from vandal.verify.replay import Trace, replay_detailed

    trace = Trace.load(args.trace)
    policy = _policy(args)
    _print_policy(policy)
    result, sb, _ = replay_detailed(
        trace.seed,
        trace.moves,
        days=trace.days,
        sandbox=partial(new_sandbox, args.profile, policy=policy),
    )
    print(f"trace {trace.name}: {len(trace.moves)} moves, seed {trace.seed}, {trace.days} days")
    for m in trace.moves:
        params = " ".join(f"{k}={v}" for k, v in m.params.items())
        print(f"  @{m.at:<3} {m.kind} {params}".rstrip())
    if not result.violations:
        print("no violations: the controls held")
    else:
        print(f"VIOLATED {', '.join(result.violated)}")
        for v in result.violations:
            print(f"  {v.invariant}  {v.message}")
    print(f"exposure    ${result.exposure / 100:,.2f}  ({result.exposure} cents)")
    print(f"state_hash  {result.state_hash}")
    _print_diagnosis(sb, result.violations)
    return 0


def _timeline(state, subjects: set[str]) -> list[str]:
    """The events behind the violating payments: approval, change, execution, settlement."""
    pays = {s for s in subjects if s in state.payments}
    invoices = {state.payment_instructions[state.payments[p].instruction].invoice for p in pays}
    accounts = {
        state.payment_instructions[state.payments[p].instruction].payee_account for p in pays
    }
    keep = (
        "approval.requested",
        "approval.granted",
        "channel.received",
        "change_request.created",
        "vendor.bank_changed",
        "instruction.built",
        "payment.submitted",
        "bank.settled",
    )
    lines = []
    for e in state.events:
        if e.kind not in keep:
            continue
        blob = str(e.payload)
        if any(x in blob for x in invoices | pays | accounts) or e.kind == "channel.received":
            what = {
                "approval.requested": lambda p: f"{p['request']['subject']} waits in the inbox",
                "approval.granted": lambda p: (
                    f"{p['approval']['subject']} approved by {p['approval']['approver']} to "
                    f"{p['approval']['approved_instruction']['payee_account']}"
                ),
                "channel.received": lambda p: (
                    f"{p['message']['channel']} from {p['message']['sender']}: "
                    f"{p['message']['subject']}"
                ),
                "change_request.created": lambda p: (
                    f"{p['request']['id']} {p['request']['status']} for {p['request']['vendor']}"
                ),
                "vendor.bank_changed": lambda p: f"vendor master now pays {p['account']['id']}",
                "instruction.built": lambda p: (
                    f"{p['payment']['id']} built to {p['instruction']['payee_account']} "
                    f"for {p['instruction']['amount']}"
                ),
                "payment.submitted": lambda p: f"{p['payment']} submitted",
                "bank.settled": lambda p: f"{p['transaction']['payment']} settled",
            }[e.kind](e.payload)
            lines.append(f"  day {e.day}  {e.id}  {e.kind:<23} {what}")
    return lines


def _print_diagnosis(sb, violations) -> None:
    from vandal.synth.coverage import diagnose
    from vandal.verify.invariants import Limits

    d = diagnose(sb.run.state, violations, Limits.from_profile(sb.profile))
    if d is None:
        return
    also = f" (also: {', '.join(d.also)})" if d.also else ""
    print(f"diagnosis: {d.gap} at the {d.link} link of {d.payment}{also}")
    print(f"  {d.reason}")
    for ln in d.chain.links:
        print(f"  {ln.name:<10} {ln.status:<9} {ln.gap or '':<22} {ln.reason}")
    print(f"  cites {', '.join(d.cites)}")


def cmd_search(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import new_sandbox
    from vandal.search.alphabet import SCENARIOS
    from vandal.search.bfs import search
    from vandal.search.minimize import minimize_trace
    from vandal.twin.profile import load_profile
    from vandal.verify.replay import replay, replay_detailed

    scenario = SCENARIOS[args.scenario]
    policy = _policy(args)
    _print_policy(policy)
    findings = _lint_policy(policy, load_profile(args.profile))
    for f in findings:
        print(f"  lint {f}")
    if findings and not args.no_lint:
        print("rejected by lint; pass --no-lint to search it anyway")
        return 2
    factory = partial(new_sandbox, args.profile, policy=policy)
    result = search(
        factory,
        scenario,
        seed=args.seed,
        depth=args.depth,
        workers=args.workers,
        exhaustive=args.exhaustive,
    )
    print(f"scenario {scenario.name}: {scenario.description}")
    print(
        f"  alphabet          {result.alphabet} moves, depth <= {result.depth}, "
        f"{scenario.days} days, workers {result.workers}"
    )
    print(f"  explored          {result.explored} sequences (per depth: {result.levels})")
    print(
        f"  deduped           {result.deduped} by state hash, {result.pruned} skipped by "
        "partial-order reduction"
    )
    print(
        f"  throughput        {result.runs_per_second:,.0f} runs/s, "
        f"{result.ms_per_run:.2f} ms/run, {result.seconds:.2f}s"
    )
    if result.best is None:
        print(f"no violations within depth {result.depth}")
        return 0
    n, shortest = len(result.findings), len(result.best.moves)
    print(f"  violating         {n} sequences (shortest: {shortest} moves)")

    def violated(moves):
        return set(replay(args.seed, moves, sandbox=factory, days=scenario.days).violated)

    minimal = minimize_trace(result.best.moves, violated)
    final, sb, _ = replay_detailed(args.seed, minimal, sandbox=factory, days=scenario.days)
    print(f"minimal counterexample ({len(minimal)} move{'s' if len(minimal) != 1 else ''}):")
    for m in minimal:
        params = " ".join(f"{k}={v}" for k, v in m.params.items())
        print(f"  @{m.at:<3} {m.kind} {params}".rstrip())
    print(f"VIOLATED {', '.join(final.violated)}  exposure ${final.exposure / 100:,.2f}")
    for v in final.violations:
        print(f"  {v.invariant}  {v.message}")
    print("timeline:")
    for line in _timeline(sb.run.state, {v.subject for v in final.violations}):
        print(line)
    _print_diagnosis(sb, final.violations)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import intake_extractor, new_sandbox
    from vandal.verify.suite import verify

    policy = load_policy(args.policy)
    parent = load_policy(args.parent or policy.parent or "v0")
    _print_policy(policy)
    pack = verify(
        policy,
        parent,
        lambda p: partial(new_sandbox, args.profile, policy=p),
        profile=args.profile,
        seed=args.seed,
        depth=args.depth,
        workers=args.workers,
        scenarios=args.scenario.split(","),
        intake=intake_extractor(args.profile, use_llm=not args.no_llm),
    )
    print(f"verification of {pack.version} against {parent.version}:")
    for c in pack.checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.number} {c.name:<11} {c.detail}")
    if pack.counterexample:
        cx = pack.counterexample
        moves = "; ".join(f"{m.kind}@{m.at}" for m in cx.moves)
        print(f"  counterexample (under {cx.found_under}): {moves} -> {', '.join(cx.violated)}")
    if pack.diagnosis:
        print(f"  diagnosis: {pack.diagnosis['gap']} at the {pack.diagnosis['link']} link")
    for line in pack.candidates[0].lint:
        print(f"  lint {line}")
    before, after = pack.metrics["before"], pack.metrics["after"]
    print(f"scorecard            {before.policy:>10} {after.policy:>10}")
    rows = [
        ("sequences explored", before.sequences_explored, after.sequences_explored),
        ("violations found", before.violations_found, after.violations_found),
        ("attack success", f"{before.attack_success_rate:.0%}", f"{after.attack_success_rate:.0%}"),
        ("exposure", f"${before.exposure / 100:,.0f}", f"${after.exposure / 100:,.0f}"),
        (
            "false positives",
            f"{before.false_positive_rate:.0%}",
            f"{after.false_positive_rate:.0%}",
        ),
        ("holds", before.holds, after.holds),
        (
            "broken invariants",
            ",".join(before.broken_invariants) or "-",
            ",".join(after.broken_invariants) or "-",
        ),
        ("extraction accuracy", _pct(before.extraction_accuracy), _pct(after.extraction_accuracy)),
        ("GL-coding accuracy", _pct(before.gl_coding_accuracy), _pct(after.gl_coding_accuracy)),
    ]
    for name, b, a in rows:
        print(f"  {name:<18} {b!s:>10} {a!s:>10}")
    for cls in sorted(after.attack_success):
        b, a = before.attack_success.get(cls), after.attack_success[cls]
        print(
            f"  {cls:<26} {f'{b.succeeded}/{b.attempts}' if b else '-':>2} "
            f"{f'{a.succeeded}/{a.attempts}':>10}"
        )
    path = pack.write(args.out)
    print(f"{'approvable' if pack.approvable else 'NOT approvable'}: wrote {path}")
    return 0 if pack.approvable else 1


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def cmd_synth(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import intake_extractor, new_sandbox
    from vandal.synth.cegis import cegis
    from vandal.synth.propose import LLMProposer, SweepProposer
    from vandal.twin.profile import load_profile
    from vandal.verify.evidence_pack import Candidate
    from vandal.verify.suite import verify

    profile = load_profile(args.profile)
    parent = load_policy(args.policy)
    proposer = SweepProposer(profile) if args.no_llm else LLMProposer(profile)
    print(
        f"synthesizing from {parent.version} for scenario {args.scenario} "
        f"({'sweep' if args.no_llm else 'LLM, sweep fallback'}, "
        f"depth {args.depth}, up to {args.max_iterations} iterations)"
    )

    def show(e) -> None:
        print(f"  it{e.iteration} {e.outcome:<14} {e.candidate}")
        print(f"      {e.detail}" + (f"  [score {e.score:,}]" if e.score is not None else ""))

    def factory_for(p):
        return partial(new_sandbox, args.profile, policy=p)

    result = cegis(
        parent,
        factory_for,
        profile=profile,
        proposer=proposer,
        seed=args.seed,
        depth=args.depth,
        workers=args.workers,
        max_iterations=args.max_iterations,
        version=args.version,
        on_entry=show,
        scenario=args.scenario,
    )
    for note in result.notes:
        print(f"  note: {note}")
    refuted = sum(1 for e in result.log if e.outcome != "survived")
    print(f"{result.status}: {result.reason} ({len(result.log)} candidates, {refuted} refuted)")
    if result.status != "repaired" or result.policy is None:
        return 1
    for line in result.chosen:
        print(f"  + {line}")
    candidates = [
        Candidate(
            source=f"cegis it{e.iteration} ({e.source})",
            controls=[*e.base, e.candidate],
            lint=e.lint,
            result=f"{e.outcome}: {e.detail}",
        )
        for e in result.log
    ]
    pack = verify(
        result.policy,
        parent,
        factory_for,
        profile=args.profile,
        seed=args.seed,
        depth=args.depth,
        workers=args.workers,
        candidates=candidates,
        scenarios=sorted({"a", args.scenario}),  # a repair must not reopen Scenario A
        intake=intake_extractor(args.profile, use_llm=not args.no_llm),
    )
    for c in pack.checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.number} {c.name:<11} {c.detail}")
    path = pack.write(args.out)
    print(f"{'approvable' if pack.approvable else 'NOT approvable'}: wrote {path}")
    return 0 if pack.approvable else 1


def cmd_intake(args: argparse.Namespace) -> int:
    """O1: every planted messy-document item through the LLM Operator's intake, scored against
    the answer key. Exit 0 when both accuracies reach the target (DESIGN: 90% or better)."""
    from vandal.sandbox import intake_extractor, new_sandbox
    from vandal.verify.messy import messy_items, score

    sb = new_sandbox(args.profile, seed=args.seed)
    items = messy_items(sb.run.state, sb.profile)
    acc = score(items, intake_extractor(sb.profile, use_llm=not args.no_llm), sb.run.state)
    formats = {}
    for item in items:
        formats[item.format] = formats.get(item.format, 0) + 1
    print(
        f"{sb.run.state.company}: {acc.items} messy-document items "
        f"({', '.join(f'{n} {f}' for f, n in sorted(formats.items()))}; "
        f"{sum(i.twisted for i in items)} coded outside the vendor's default account)"
    )
    paths = ", ".join(f"{n} {s}" for s, n in sorted(acc.sources.items()))
    print(f"  intake path          {paths}")
    print(
        f"  extraction accuracy  {acc.extraction_accuracy:.1%} "
        f"({acc.fields_correct}/{acc.fields_total} fields)"
    )
    for fmt, value in acc.by_format.items():
        print(f"    {fmt:<18} {value:.1%}")
    print(f"  GL-coding accuracy   {acc.gl_coding_accuracy:.1%} ({acc.gl_correct}/{acc.gl_total})")
    for miss in acc.misses:
        print(f"  miss  {miss}")
    if args.show:
        for item in items:
            if item.id == args.show:
                print(f"\n--- {item.id} ({item.format}) from {item.message.sender}")
                print(f"Subject: {item.message.subject}\n\n{item.message.body}")
    ok = acc.extraction_accuracy >= args.target and acc.gl_coding_accuracy >= args.target
    print(f"{'meets' if ok else 'BELOW'} the {args.target:.0%} target")
    return 0 if ok else 1


def _short(move) -> str:
    params = " ".join(f"{k}={v}" for k, v in move.params.items() if k != "text")
    return f"@{move.at:<3} {move.kind} {params}"


def cmd_inject(args: argparse.Namespace) -> int:
    """Preview a user-authored threat, run it on a fresh clone, search k moves around it, and
    send any violation into diagnose -> CEGIS."""
    from functools import partial

    from vandal.sandbox import new_sandbox
    from vandal.search import red
    from vandal.search.alphabet import SCENARIOS
    from vandal.search.bfs import search
    from vandal.search.minimize import minimize_trace
    from vandal.synth.cegis import cegis
    from vandal.synth.coverage import diagnose
    from vandal.synth.propose import LLMProposer, SweepProposer
    from vandal.twin.profile import load_profile
    from vandal.verify.invariants import Limits
    from vandal.verify.replay import Trace, replay, replay_detailed

    policy = _policy(args)
    profile = load_profile(args.profile)

    def factory_for(p):
        return partial(new_sandbox, args.profile, policy=p)

    factory = factory_for(policy)
    if args.trace:  # compose inject: raw moves plus labels
        trace = Trace.load(args.trace)
        plan = red.ThreatPlan(
            description=args.description or trace.name,
            moves=trace.moves,
            labels=trace.labels,
            scenario=args.scenario or "a",
            source="trace",
        )
    else:
        if not args.description:
            print("vandal inject: give a description or --trace", file=sys.stderr)
            return 2
        try:
            plan = red.plan(args.description, factory, args.seed, use_llm=not args.no_llm)
        except ValueError as err:
            print(f"vandal inject: {err}", file=sys.stderr)
            return 2
        if args.scenario:
            plan.scenario = args.scenario
    _print_policy(policy)
    print(f"threat ({plan.source}): {plan.description}")
    for move in plan.moves:
        print(f"  {_short(move)}")
        if text := move.params.get("text"):
            print(f'        "{str(text).splitlines()[0][:90]}"')
    for note in plan.notes:
        print(f"  note: {note}")
    if args.dry_run:
        return 0

    def violated(moves) -> set[str]:
        return set(replay(args.seed, moves, sandbox=factory, labels=plan.labels).violated)

    result = replay(args.seed, plan.moves, sandbox=factory, labels=plan.labels)
    if result.violations:
        print(
            f"on a fresh clone: VIOLATED {', '.join(result.violated)}  "
            f"exposure ${result.exposure / 100:,.2f}"
        )
        moves = minimize_trace(plan.moves, violated)
    else:
        print("on a fresh clone: no violation")
        found = search(
            factory,
            SCENARIOS[plan.scenario],
            seed=args.seed,
            depth=args.depth,
            workers=args.workers,
            around=plan.moves,
            labels=plan.labels,
        )
        print(
            f"  searched {found.explored} sequences with up to {args.depth} moves around it "
            f"(scenario {plan.scenario})"
        )
        if found.best is None:
            print("controls held")
            return 0
        moves = minimize_trace(found.best.moves, violated)
        needed = [m for m in plan.moves if m in moves]
        print(
            f"  search found a violation in {len(found.best.moves)} moves"
            + ("" if needed else "; the injected moves weren't needed for it")
        )
    final, sb, _ = replay_detailed(args.seed, moves, sandbox=factory, labels=plan.labels)
    print(f"minimal counterexample ({len(moves)} moves):")
    for move in moves:
        print(f"  {_short(move)}")
    print(f"VIOLATED {', '.join(final.violated)}  exposure ${final.exposure / 100:,.2f}")
    d = diagnose(sb.run.state, final.violations, Limits.from_profile(sb.profile))
    if d is None:
        print("diagnosis: every chain is covered; nothing to attach a control to")
        return 1
    print(f"diagnosis: {d.gap} at the {d.link} link of {d.payment}")
    print(f"  {d.reason}")
    if args.no_repair:
        return 1
    proposer = SweepProposer(profile) if args.no_llm else LLMProposer(profile)
    print(f"repairing (CEGIS from {policy.version}, depth {args.synth_depth}):")
    r = cegis(
        policy,
        factory_for,
        profile=profile,
        proposer=proposer,
        seed=args.seed,
        depth=args.synth_depth,
        workers=args.workers,
        version=f"{policy.version}-inject",
        on_entry=lambda e: print(f"  it{e.iteration} {e.outcome:<14} {e.candidate}"),
        start=moves,
        start_labels=plan.labels,
        scenario=plan.scenario,
    )
    print(f"{r.status}: {r.reason}")
    for line in r.chosen:
        print(f"  + {line}")
    return 1


IMPLEMENTED: dict[str, Callable[[argparse.Namespace], int]] = {
    "rebuild": cmd_rebuild,
    "synth": cmd_synth,
    "verify": cmd_verify,
    "inject": cmd_inject,
    "search": cmd_search,
    "seed": cmd_seed,
    "run": cmd_run,
    "attack": cmd_attack,
    "intake": cmd_intake,
}


def build_parser() -> argparse.ArgumentParser:
    from vandal.twin.seed import DEFAULT_SEED

    parser = argparse.ArgumentParser(prog="vandal", description="Vandal CLI")
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, (help_text, _slice) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        if name in ("seed", "run", "attack", "search", "verify", "synth", "inject", "intake"):
            cmd.add_argument("--profile", default="bayline", help="profile name or YAML path")
            cmd.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name in ("run", "verify", "intake"):
            cmd.add_argument(
                "--no-llm", action="store_true", help="intake by the deterministic reader only"
            )
        if name == "intake":
            cmd.add_argument("--target", type=float, default=0.9, help="accuracy to reach")
            cmd.add_argument("--show", help="print one item by id, e.g. MSY-003")
        if name in ("run", "attack", "search", "verify", "synth", "inject"):
            cmd.add_argument("--policy", help="v0, a name under policies/, or a JSON path")
        if name == "synth":
            cmd.add_argument("--no-llm", action="store_true", help="enumerative sweep only")
            cmd.add_argument("--max-iterations", type=int, default=4)
            cmd.add_argument("--version", default="v1-synth", help="name of the new policy")
        if name in ("verify", "synth"):
            cmd.add_argument("--out", default="evidence", help="directory for the evidence pack")
            cmd.add_argument(
                "--depth", type=int, default=int(os.environ.get("SEARCH_DEPTH", DEFAULT_DEPTH))
            )
            cmd.add_argument(
                "--workers",
                type=int,
                default=int(os.environ.get("SEARCH_WORKERS", min(8, os.cpu_count() or 1))),
            )
        if name == "verify":
            cmd.add_argument("--parent", help="policy to compare against (default: its parent)")
            cmd.add_argument("--scenario", default="a", help="scenarios to re-search, e.g. a,b")
        if name == "synth":
            cmd.add_argument("--scenario", default="a", help="threat family to repair")
        if name == "run":
            cmd.add_argument("--days", type=int, default=5)
            cmd.add_argument(
                "--operator",
                choices=("reference", "llm"),
                default="reference",
                help="the deterministic reference Operator, or the LLM Operator (O1)",
            )
            cmd.add_argument(
                "--persist",
                action="store_true",
                help="write the run and its events to the database",
            )
        if name in ("run", "rebuild"):
            cmd.add_argument("--db", help="database URL (default: DATABASE_URL, else SQLite)")
        if name == "rebuild":
            cmd.add_argument("run_id")
        if name == "search":
            cmd.add_argument("--scenario", default="a", help="scenario name (search/alphabet.py)")
            cmd.add_argument(
                "--depth", type=int, default=int(os.environ.get("SEARCH_DEPTH", DEFAULT_DEPTH))
            )
            cmd.add_argument(
                "--workers", type=int, default=int(os.environ.get("SEARCH_WORKERS", 1))
            )
            cmd.add_argument(
                "--no-lint", action="store_true", help="search a policy even if lints reject it"
            )
            cmd.add_argument(
                "--exhaustive",
                action="store_true",
                help="explore every depth, not just up to the first violations",
            )
        if name == "attack":
            cmd.add_argument("--trace", required=True, help="path to a trace JSON file")
        if name == "inject":
            cmd.add_argument("description", nargs="?", help="the threat, in plain language")
            cmd.add_argument("--trace", help="compose inject: a trace JSON (moves + labels)")
            cmd.add_argument("--scenario", help="search window around it (default: inferred)")
            cmd.add_argument("--depth", type=int, default=1, help="moves searched around it")
            cmd.add_argument("--synth-depth", type=int, default=2, help="CEGIS search depth")
            cmd.add_argument(
                "--workers", type=int, default=int(os.environ.get("SEARCH_WORKERS", 1))
            )
            cmd.add_argument("--no-llm", action="store_true", help="keywords and templates")
            cmd.add_argument("--no-repair", action="store_true", help="diagnose, don't repair")
            cmd.add_argument("--dry-run", action="store_true", help="preview the moves only")
    return parser


def main(argv: list[str] | None = None) -> int:
    from vandal.llm import load_env

    load_env()  # backend/.env before the parser reads SEARCH_DEPTH and friends
    args, _rest = build_parser().parse_known_args(argv)
    if args.command in IMPLEMENTED:
        return IMPLEMENTED[args.command](args)
    _help, slice_id = COMMANDS[args.command]
    print(f"vandal {args.command}: not implemented yet (lands in {slice_id})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
