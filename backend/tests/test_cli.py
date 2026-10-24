from __future__ import annotations

import pytest

from vandal.cli import COMMANDS, build_parser, main


def test_help_lists_every_command(capsys) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--help"])
    out = capsys.readouterr().out
    for name in ("seed", "run", "attack", "search", "synth", "verify", "inject"):
        assert name in out
    assert set(COMMANDS) == {
        "seed",
        "run",
        "attack",
        "search",
        "synth",
        "verify",
        "inject",
        "rebuild",
        "intake",
    }


def test_stub_commands_exit_nonzero() -> None:
    assert main(["inject"]) == 2
