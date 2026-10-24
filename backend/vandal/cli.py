"""vandal seed | run | attack | search | synth | verify | inject"""

from __future__ import annotations

import argparse
import sys

COMMANDS: dict[str, tuple[str, str]] = {
    "seed": ("Print the seeded company summary", "R1"),
    "run": ("Run legitimate operations for N business days", "R2"),
    "attack": ("Replay a hand-written adversary trace", "R3"),
    "search": ("Bounded adversarial search for violations", "R4"),
    "synth": ("Diagnose and synthesize a control (CEGIS)", "R8"),
    "verify": ("Run the verification suite against a policy", "R7"),
    "inject": ("Run a user-authored threat in plain language", "R9"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vandal", description="Vandal Sandbox CLI")
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, (help_text, _slice) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    args, _rest = build_parser().parse_known_args(argv)
    _help, slice_id = COMMANDS[args.command]
    print(f"vandal {args.command}: not implemented yet (lands in {slice_id})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
