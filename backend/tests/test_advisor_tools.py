"""LLM-free tests of the advisor plumbing: profile merging, engine bridge, product-code sanitiser, handoff storage."""
import os

import pytest

from app import db
from app.advisor import service, tools as T
from app.engine import BudgetStatus


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("UDYAM_DB_PATH", str(tmp_path / "test.sqlite"))
    db.init_db()


def test_profile_merge_unions_lists_and_resolves_city():
    p = T.apply_profile_update({}, {"business_type": "Kirana store", "city": "Nashik", "needs": ["internet"]})
    assert p["city_tier"] == 2 and p["state"] == "Maharashtra"
    p = T.apply_profile_update(p, {"needs": ["cctv"], "employee_count": 3, "has_gstin": False, "has_udyam": True})
    assert p["needs"] == ["internet", "cctv"] and p["gstin_status"] == "unknown"
    assert T.missing_fields(p) == []


def test_change_of_mind_moves_need_between_lists():
    p = T.apply_profile_update({}, {"needs": ["cctv", "whatsapp"]})
    p = T.apply_profile_update(p, {"excluded_needs": ["cctv"]})
    assert p["needs"] == ["whatsapp"] and p["excluded_needs"] == ["cctv"]
    p = T.apply_profile_update(p, {"needs": ["cctv"]})
    assert "cctv" in p["needs"] and p["excluded_needs"] == []


def test_unknown_city_asks_for_tier():
    p = T.apply_profile_update({}, {"city": "Rajkot", "business_type": "Salon", "employee_count": 2, "has_gstin": True})
    assert any(m.startswith("city_tier") for m in T.missing_fields(p))
    p = T.apply_profile_update(p, {"city_tier": 2})
    assert T.missing_fields(p) == []


def test_engine_bridge_handles_strings_and_unknown_values():
    p = T.apply_profile_update({}, {"business_type": "Dental clinic", "city": "Mumbai", "employee_count": 6,
                                    "has_gstin": True, "gstin_status": "cancelled", "needs": ["whatsapp"],
                                    "requested_products": ["P03"], "monthly_budget_inr": 3000})
    rec = T.run_recommendation(p)
    names = {i.product_id for i in rec.items}
    assert "P15" not in names and "P03" not in names
    assert rec.kyc_path != "gstin"
    llm_view = T.recommendation_for_llm(rec)
    assert "P0" not in str(llm_view) and llm_view["monthly_total_inr"] == rec.pricing.monthly_total_inr
    assert rec.pricing.budget_status in (BudgetStatus.TRIMMED, BudgetStatus.OVER_MINIMUM, BudgetStatus.WITHIN)


def test_sanitiser_replaces_leaked_codes():
    text = "I recommend P01 and P15 for you, total P99 is not a product."
    out = service._sanitise(text)
    assert "Biz Fibre 100" in out and "WhatsApp Business API Starter" in out and "P99" in out


def test_session_roundtrip_and_handoff_storage():
    session = service.create_session()
    session["profile"] = T.apply_profile_update({}, {"business_type": "Bakery", "city": "Pune", "employee_count": 4, "has_gstin": True})
    out, err = service.execute_tool(session, "get_recommendation", {})
    assert not err and session["stage"] == "recommended" and session["recommendation"]["items"]
    out, err = service.execute_tool(session, "create_handoff_lead",
                                    {"reason": "customer_hesitant", "summary": "Bakery in Pune, wants to think.", "callback": "6pm"})
    assert not err and session["handoff_id"]
    out2, _ = service.execute_tool(session, "create_handoff_lead", {"reason": "other", "summary": "again", "callback": None})
    assert "already exists" in out2
    service._save(session)
    loaded = service.get_session(session["id"])
    assert loaded["stage"] == "handoff" and loaded["recommendation"]["pricing"]["monthly_total_inr"] > 0
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM handoff_leads").fetchall()
    assert len(rows) == 1 and rows[0]["city"] == "Pune" and rows[0]["state"] == "Maharashtra"


# ---------------------------------------------------------------------------
# a fake Claude client: proves the conversation is append-only and thinking blocks are replayed
# ---------------------------------------------------------------------------
import copy

import anthropic


def _msg(content, stop_reason):
    return anthropic.types.Message.model_validate({
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    })


class FakeClient:
    """Turn 1: thinking + update_profile tool call. Then: text reply. Records every request."""

    def __init__(self):
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs["messages"]))
        if len(self.requests) == 1:
            return _msg([
                {"type": "thinking", "thinking": "", "signature": "sig-abc"},
                {"type": "tool_use", "id": "tu_1", "name": "update_profile",
                 "input": {"business_type": "Kirana store", "city": "Nashik", "employee_count": 3, "has_gstin": False}},
            ], "tool_use")
        return _msg([{"type": "text", "text": "Got it. Do you have a Udyam registration?"}], "end_turn")


def test_history_is_append_only_and_thinking_blocks_are_replayed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = FakeClient()
    monkeypatch.setattr(service, "client", lambda: fake)
    session = service.create_session()
    state = service.handle_message(session, "Kirana in Nashik, 3 log, GST nahi hai")
    assert state["reply"].startswith("Got it") and state["profile"]["city_tier"] == 2
    first, second = fake.requests
    # the second request extends the first one unchanged (append-only prefix)
    assert second[: len(first)] == first
    # the thinking block (empty text + signature) is sent back exactly as received
    assert second[1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    assert second[2]["content"][0]["type"] == "tool_result"
    # a second customer turn still extends the stored history without edits
    stored = copy.deepcopy(session["messages"])
    service.handle_message(session, "Haan, Udyam hai")
    assert fake.requests[-1][: len(stored)] == stored


def test_no_key_raises_llm_unavailable_and_leaves_session_untouched(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session = service.create_session()
    with pytest.raises(service.LLMUnavailable):
        service.handle_message(session, "hello")
    assert session["messages"] == [] and session["transcript"] == []


def test_turn_cap_offers_human_without_calling_the_api(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(service, "client", lambda: (_ for _ in ()).throw(AssertionError("API must not be called")))
    session = service.create_session()
    session["transcript"] = [{"role": "user", "text": "x"}] * service.MAX_CUSTOMER_TURNS
    state = service.handle_message(session, "one more")
    assert "Talk to a person" in state["reply"]


# ---------------------------------------------------------------------------
# guided (tap-to-answer) advisor - no LLM at all
# ---------------------------------------------------------------------------
def test_guided_answers_run_the_engine_and_handoff_writes_a_summary(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/health").json()["llm_available"] is False
        sid = c.post("/api/advisor/sessions", json={}).json()["session_id"]
        assert c.post(f"/api/advisor/sessions/{sid}/messages", json={"message": "hi"}).status_code == 503
        answers = {"business_type": "Kirana store", "city": "Nashik", "employee_count": 3, "num_sites": 1,
                   "has_gstin": False, "has_udyam": True, "needs": ["internet", "mobile_lines", "whatsapp", "cctv"],
                   "num_cameras": 2}
        state = c.post(f"/api/advisor/sessions/{sid}/guided", json={"answers": answers, "summary_line": "Kirana, Nashik"}).json()
        rec = state["recommendation"]
        ids = {i["product_id"] for i in rec["items"]}
        assert {"P01", "P07", "P23"} <= ids and "P15" not in ids          # WhatsApp API needs GSTIN
        assert rec["kyc_path"] == "udyam_only" and state["stage"] == "recommended"
        # changing an answer replaces the profile rather than accumulating stale needs
        state = c.post(f"/api/advisor/sessions/{sid}/guided", json={"answers": {**answers, "needs": ["internet"], "excluded_needs": ["mobile_lines"]}}).json()
        ids = {i["product_id"] for i in state["recommendation"]["items"]}
        assert "P23" not in ids and "P07" not in ids
        h = c.post(f"/api/advisor/sessions/{sid}/handoff", json={"reason": "wants_human", "callback": "after 6 pm"}).json()
        assert h["stage"] == "handoff" and h["handoff_id"]
        lead = c.get("/api/handoffs", params={"city": "Nashik"}).json()[0]
        assert "Kirana store in Nashik" in lead["summary"] and "Udyam only" in lead["summary"] and lead["contact"] == "after 6 pm"


# --- fixes found by the first live run (7 Nov 2026) -------------------------------------------
def test_tool_schemas_fit_strict_limits():
    """The API rejects strict tools with >16 union-typed or >24 optional params, or numeric bounds."""
    import json as _json
    blob = _json.dumps(T.TOOLS)
    assert '"anyOf"' not in blob and '"minimum"' not in blob and '"maximum"' not in blob
    optional = sum(len(set(t["input_schema"]["properties"]) - set(t["input_schema"]["required"])) for t in T.TOOLS)
    assert optional <= 24


def test_quantities_list_maps_to_profile_fields():
    p = T.apply_profile_update({}, {"quantities": [{"item": "mobile_lines", "count": 2}, {"item": "cctv_cameras", "count": -4}]})
    assert p["num_mobile_lines"] == 2 and p["num_cameras"] == 0


def test_cancelled_gstin_implies_has_gstin():
    p = T.apply_profile_update({}, {"gstin_status": "cancelled", "has_udyam": True})
    assert p["has_gstin"] is True
    assert T.to_business_profile({**p, "business_type": "Boutique", "employee_count": 3}).gstin_usable is False


def test_llm_view_has_subtotal_and_addon_quantity():
    rec = T.run_recommendation({"business_type": "Kirana store", "city": "Nashik", "city_tier": 2, "employee_count": 3,
                                "has_gstin": True, "needs": ["internet"]})
    view = T.recommendation_for_llm(rec)
    optional = sum(i["monthly_inr"] for i in view["items"] if i["optional"])
    assert view["monthly_total_without_optional_inr"] == view["monthly_total_inr"] - optional
    assert all("quantity" in a and "unit_price_inr" in a for a in view["add_ons"])


def test_leased_line_warns_about_site_survey():
    rec = T.run_recommendation({"business_type": "Auto-parts unit", "city": "Nashik", "city_tier": 2, "employee_count": 40,
                                "has_gstin": True, "needs": ["dedicated_internet"]})
    assert any(i.product_id == "P05" for i in rec.items)
    assert any("site survey" in w for w in rec.warnings)


def test_callback_given_after_handoff_updates_lead():
    session = service.create_session()
    service.execute_tool(session, "create_handoff_lead", {"reason": "wants_human", "summary": "Hardware store, Nagpur", "callback": ""})
    service.execute_tool(session, "update_profile", {"contact_phone": "98xxxxxx10"})
    with db.connect() as conn:
        row = conn.execute("SELECT contact FROM handoff_leads WHERE id = ?", (session["handoff_id"],)).fetchone()
    assert row["contact"] == "98xxxxxx10"
