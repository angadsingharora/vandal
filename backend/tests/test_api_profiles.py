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


def test_your_own_vendors_take_the_place_of_the_base_companys() -> None:
    with client() as c:
        made = c.post(
            "/profiles",
            json={
                "company_name": "Harbor Dental Group",
                "vendors": [
                    {"name": "Acme Dental Supply", "domain": "acmedental.com"},
                    {"name": "Bright Smiles Lab"},
                ],
            },
        ).json()
        assert made["company"] == "Harbor Dental Group"
        assert made["vendors"] == 25  # the base's count: renamed in place, not added
        assert made["vendor_names"][:2] == ["Acme Dental Supply", "Bright Smiles Lab"]
        assert made["vendor_names"][2] == "Coastal HVAC Services"
        exported = c.get(f"/profiles/{made['name']}/export").json()["profile"]
        assert exported["vendors"][0]["domain"] == "acmedental.com"
        assert exported["vendors"][1]["domain"] == "brightsmileslab.com"
        assert exported["vendors"][0]["id"] == "V-001"  # structure kept
        # the renamed company seeds and runs
        run = c.post("/runs", json={"profile": made["name"]}).json()
        vendors = {v["name"] for v in c.get(f"/runs/{run['run_id']}/entities").json()["vendors"]}
        assert "Acme Dental Supply" in vendors and "Bayside Plumbing" not in vendors
        # bounds
        assert c.post("/profiles", json={"vendors": [{"name": "x"}] * 26}).status_code == 400
        twice = c.post("/profiles", json={"vendors": [{"name": "Same"}, {"name": "same"}]})
        assert twice.status_code == 400 and "twice" in twice.json()["detail"]
        bad = c.post("/profiles", json={"vendors": [{"name": "A", "domain": "not a domain"}]})
        assert bad.status_code == 400 and "domain" in bad.json()["detail"]


def test_a_company_survives_as_a_file() -> None:
    with client() as c:
        made = c.post(
            "/profiles",
            json={"company_name": "Keep Me Inc", "approval": {"threshold": 1_000_000}},
        ).json()
        exported = c.get(f"/profiles/{made['name']}/export").json()
        assert exported["company"] == "Keep Me Inc"
        assert exported["profile"]["approval_matrix"]["threshold"] == 1_000_000
        assert c.get("/profiles/nope/export").status_code == 404
        # bring it back under another name, as a new process would
        back = c.post("/profiles/import", json={"name": "restored", "profile": exported["profile"]})
        assert back.status_code == 200, back.text
        assert back.json()["name"] == "restored"
        assert back.json()["approval"]["threshold"] == 1_000_000
        assert c.post("/runs", json={"profile": "restored"}).status_code == 200
        # a built-in exports too, and imports under its company name
        bay = c.get("/profiles/bayline/export").json()["profile"]
        assert (
            c.post("/profiles/import", json={"profile": bay}).json()["name"]
            == "bayline-property-group"
        )
        # validated like a file, bounded like a custom company
        assert c.post("/profiles/import", json={"profile": {"company": {}}}).status_code == 400
        huge = {**bay, "generation": {**bay["generation"], "invoices": 10_000}}
        assert c.post("/profiles/import", json={"profile": huge}).status_code == 400
