"""Slow tests (full searches, CEGIS, verification packs) are skipped by default so the everyday
suite stays fast. Run everything with `uv run pytest --slow` (or VANDAL_SLOW=1).

The suite never calls Claude or Moss: backend/.env isn't loaded, the API and Moss keys are
cleared, and each test gets an empty LLM cache, job cache, and pattern cache, so every caller
takes its deterministic path and no test leaves a recording in the repo. The live checks run
only with VANDAL_LIVE_LLM=1 (test_llm.py) or VANDAL_LIVE_MOSS=1 (test_patterns.py)."""

from __future__ import annotations

import os

import pytest

# Before any test module imports vandal.api.main, whose module-level app would load backend/.env.
os.environ["VANDAL_DOTENV"] = "0"
for _var in (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "DEMO_PLAYBACK",
    "MOSS_PROJECT_ID",
    "MOSS_PROJECT_KEY",
):
    os.environ.pop(_var, None)


@pytest.fixture(autouse=True)
def _offline_llm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from vandal import llm

    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    monkeypatch.setenv("JOB_CACHE_DIR", str(tmp_path / "job_cache"))
    monkeypatch.setenv("PATTERN_CACHE_DIR", str(tmp_path / "pattern_cache"))
    monkeypatch.setattr(llm, "_client_cache", None)
    yield
    # custom companies (POST /profiles) live in the process; no test sees another's
    from vandal.twin.profile import clear_custom_profiles

    clear_custom_profiles()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        help="also run slow tests: full searches, CEGIS, verification packs",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: takes seconds; skipped unless --slow")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--slow") or os.environ.get("VANDAL_SLOW"):
        return
    skip = pytest.mark.skip(reason="slow: run with --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
