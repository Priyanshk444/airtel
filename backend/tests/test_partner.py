"""Propensity model honesty and partner endpoints."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.propensity import get_model


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("UDYAM_DB_PATH", str(tmp_path / "p.sqlite"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db.init_db()


def test_model_metrics_are_from_a_held_out_split_and_beat_baseline():
    m = get_model()
    met = m.metrics
    assert met["test_leads"] == 1000 and 0.05 < met["activation_rate_baseline"] < 0.1
    assert met["roc_auc"] > 0.6                  # clearly better than random, honestly modest
    assert met["lift_top10pct"] > 1.5            # calling the top decile pays off
    assert len(set(m.test_index)) == 1000
    factors = m.factors()
    assert factors and abs(factors[0]["weight"]) >= abs(factors[-1]["weight"])
    # the known planted signals should surface: GSTIN and lead source
    labels = " ".join(f["factor"] for f in factors)
    assert "Has GSTIN" in labels and "Lead source" in labels


def test_ranking_filters_and_explains():
    m = get_model()
    top = m.rank(state="Maharashtra", limit=5)
    assert len(top) == 5 and all(r["state"] == "Maharashtra" for r in top)
    assert all(r["stage_reached"] != "Activated" for r in top)
    assert all(len(r["reasons"]) == 3 for r in top)
    assert top[0]["score"] >= top[-1]["score"]
    assert m.rank(city="Nashik", segment="Professional offices", limit=3)


def test_partner_api_and_assisted_sessions():
    from app.main import app
    with TestClient(app) as c:
        model = c.get("/api/propensity/model").json()
        assert model["metrics"]["roc_auc"] > 0.6 and model["top_factors"]
        leads = c.get("/api/propensity/leads", params={"state": "Gujarat", "limit": 10}).json()
        assert len(leads) == 10 and leads[0]["reasons"]
        terr = c.get("/api/partner/territories").json()
        assert "Nashik" in terr["Maharashtra"]
        # assisted mode: a partner opens a session for a shop owner and uses the guided advisor
        s = c.post("/api/advisor/sessions", json={"assisted_by": "partner_nashik_01"}).json()
        c.post(f"/api/advisor/sessions/{s['session_id']}/guided", json={"answers": {
            "business_type": "Kirana store", "city": "Nashik", "employee_count": 2, "has_gstin": False, "has_udyam": True, "needs": ["internet"]}})
        mine = c.get("/api/partner/sessions", params={"assisted_by": "partner_nashik_01"}).json()
        assert len(mine) == 1 and mine[0]["monthly_total_inr"] and mine[0]["profile"]["city"] == "Nashik"
        assert c.get("/api/partner/sessions", params={"assisted_by": "someone_else"}).json() == []
        # handoff workflow: open -> contacted
        h = c.get("/api/handoffs", params={"status": "open"}).json()
        assert h, "seed should have open handoffs"
        updated = c.patch(f"/api/handoffs/{h[0]['id']}", json={"status": "contacted"}).json()
        assert updated["status"] == "contacted"
