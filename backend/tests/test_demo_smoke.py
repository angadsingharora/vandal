"""The whole war-room loop against the API, in process (scripts/demo_smoke.py), on the
deterministic paths: exposure $40,000 under v0, HELD and $0 under the synthesized policy, zero
legitimate payments blocked, every scorecard field filled, Reset under 1 s."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import demo_smoke  # noqa: E402

pytestmark = pytest.mark.slow


def test_the_demo_loop_end_to_end() -> None:
    with TestClient(create_app(persist=False)) as c:
        out = demo_smoke.run(c, no_llm=True, depth=2, log=lambda *_: None)
    assert out["timings"]["reset"] < 1.0
    assert out["scorecards"]["v0"]["exposure"] > 0
    assert out["scorecards"][out["version"]]["exposure"] == 0
