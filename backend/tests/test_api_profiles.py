"""The workspace's companies: the built-ins are listed, a custom one is derived from a base with
a few knobs turned, and every job that takes a profile name accepts it (api/routes_profiles.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vandal.api.main import create_app

from .test_api import wait


def client() -> TestClient:
    return TestClient(create_app(persist=False))


def test_builtins_are_listed_with_their_knobs() -> None:
    with client() as c:
        profiles = c.get("/profiles").json()
        names = [p["name"] for p in profiles]
        assert "bayline" in names
        bayline = next(p for p in profiles if p["name"] == "bayline")
        assert bayline["custom"] is False
        assert bayline["company"] == "Bayline Property Group"
        assert bayline["approval"]["threshold"] == 2_500_000
        assert bayline["generation"]["invoices"] == 80
        assert bayline["attacker"]["portal_takeover"] is False
        assert c.get("/profiles/bayline").json()["name"] == "bayline"
        assert c.get("/profiles/nope").status_code == 404
        # the threat families a search can be pointed at ride on /settings
        assert set(c.get("/settings").json()["scenarios"]) >= {"a", "b", "f"}


def test_a_custom_company_runs_everywhere_a_profile_name_goes() -> None:
    with client() as c:
        made = c.post(
            "/profiles",
            json={
                "company_name": "Harbor Dental Group",
                "approval": {"threshold": 1_000_000, "min_prior_payments": 1},
                "generation": {"invoices": 40, "pending_invoices": 12},
                "attacker": {
                    "portal_takeover": True,
                    "change_request_channels": ["email", "portal"],
                },
            },
        )
        assert made.status_code == 200, made.text
        p = made.json()
        assert p["name"] == "harbor-dental-group"
        assert p["custom"] is True
        assert p["approval"]["threshold"] == 1_000_000
        assert p["approval"]["match_tolerance_pct"] == 2  # untouched knobs keep the base's value
        assert p["generation"]["invoices"] == 40
        assert p["attacker"]["portal_takeover"] is True
        assert [x["name"] for x in c.get("/profiles").json() if x["custom"]] == [
            "harbor-dental-group"
        ]

        run = c.post(
            "/runs", json={"profile": "harbor-dental-group", "seed": 3, "policy": "v0"}
        ).json()
        assert run["company"] == "Harbor Dental Group"
        assert run["profile"] == "harbor-dental-group"
        assert sum(run["invoices"].values()) == 40

        # workers > 1: the search runs in spawned processes, which only know the custom company
        # because the factory carries the Profile object, not its name
        search = c.post(
            "/search", json={"profile": "harbor-dental-group", "seed": 3, "depth": 1, "workers": 2}
        ).json()
        assert search["meta"]["profile"] == "harbor-dental-group"
        done = wait(c, search["id"])
        assert done["status"] == "done"

        metrics = c.get("/metrics?policies=v0&depth=1&profile=harbor-dental-group&seed=3").json()
        assert "v0" in metrics["scorecards"]

        # a second company with the same name gets its own slug
        again = c.post("/profiles", json={"company_name": "Harbor Dental Group"}).json()
        assert again["name"] == "harbor-dental-group-2"


def test_custom_companies_are_bounded_and_validated() -> None:
    with client() as c:
        assert c.post("/profiles", json={"base": "nope"}).status_code == 400
        too_many = c.post("/profiles", json={"generation": {"invoices": 10_000}})
        assert too_many.status_code == 422
        upside_down = c.post(
            "/profiles", json={"generation": {"invoices": 20, "pending_invoices": 30}}
        )
        assert upside_down.status_code == 400
        assert "pending_invoices" in upside_down.json()["detail"]
        # a portal channel needs the takeover capability (twin/profile.py's own rule)
        portal = c.post(
            "/profiles", json={"attacker": {"change_request_channels": ["email", "portal"]}}
        )
        assert portal.status_code == 400
        assert "portal" in portal.json()["detail"]
        # a name nothing knows (a custom company from before a restart) is a 400 everywhere
        assert c.post("/runs", json={"profile": "gone"}).status_code == 400
        assert c.post("/search", json={"profile": "gone"}).status_code == 400
        assert c.get("/metrics?policies=v0&profile=gone").status_code == 400
        # can't shadow a built-in
        shadow = c.post("/profiles", json={"name": "bayline"}).json()
        assert shadow["name"] == "bayline-2"
