"""Quote repricing, mock checkout, order timeline and demo seed - all deterministic."""
import pytest
from fastapi.testclient import TestClient

from app import db, seed
from app.orders import STATUSES, OrderRequest, Customer, Payment, advance_order, build_timeline, create_order, get_order
from app.quote import QuoteLine, build_quote

PROFILE = {"business_type": "Kirana store", "city": "Nashik", "city_tier": 2, "employee_count": 3, "has_gstin": False, "has_udyam": True}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("UDYAM_DB_PATH", str(tmp_path / "t.sqlite"))
    db.init_db()


def test_quote_prices_from_catalogue_and_ignores_client_prices():
    q = build_quote(PROFILE, [QuoteLine(product_id="P01", quantity=1), QuoteLine(product_id="P07", quantity=2), QuoteLine(product_id="P23", quantity=3)])
    by = {i.product_id: i for i in q.items}
    assert by["P07"].monthly_inr == 598 and by["P23"].monthly_inr == 597 and by["P23"].setup_inr == 5400
    assert q.pricing.monthly_total_inr == 999 + 598 + 597 and q.pricing.setup_total_inr == 5400
    assert q.pricing.contract_months == 12 and q.pricing.expected_install_days == 5
    assert q.issues == [] and q.kyc_path == "udyam_only"


def test_quote_blocks_ineligible_and_orphan_dependencies():
    q = build_quote(PROFILE, [QuoteLine(product_id="P15", quantity=1), QuoteLine(product_id="P23", quantity=2), QuoteLine(product_id="P99", quantity=1)])
    assert q.items == []
    msgs = {i.product_id: i.message for i in q.issues}
    assert "GST" in msgs["P15"] and "internet line" in msgs["P23"] and "P99" in msgs
    assert q.pricing.monthly_total_inr == 0


def test_quote_toggle_add_on_changes_total_instantly():
    base = build_quote(PROFILE, [QuoteLine(product_id="P01", quantity=1)])
    with_wifi = build_quote(PROFILE, [QuoteLine(product_id="P01", quantity=1), QuoteLine(product_id="P22", quantity=1)])
    assert with_wifi.pricing.monthly_total_inr - base.pricing.monthly_total_inr == 399
    assert with_wifi.pricing.setup_total_inr - base.pricing.setup_total_inr == 1000


def test_timeline_dates_follow_install_days():
    from datetime import datetime, timezone
    start = datetime(2026, 7, 15, tzinfo=timezone.utc)
    tl = build_timeline(start, 14)
    assert [s["status"] for s in tl] == STATUSES
    assert tl[0]["done_at"] and all(s["done_at"] is None for s in tl[1:])
    assert tl[-1]["expected_at"] == "2026-07-29" and tl[3]["expected_at"] == "2026-07-22"


def test_checkout_creates_order_and_payment_failure_is_clean():
    req = OrderRequest(lines=[QuoteLine(product_id="P01", quantity=1), QuoteLine(product_id="P19", quantity=1)],
                       customer=Customer(business_name="Lakshmi General Store", phone="98XXXXXX01"),
                       payment=Payment(method="upi", reference="lakshmi@upi"))
    order = create_order(req, PROFILE)
    assert order["current_status"] == "ordered" and order["payment"]["status"] == "paid"
    assert order["payment"]["amount_inr"] == 2500   # POS setup fee charged now
    assert get_order(order["id"])["pricing"]["monthly_total_inr"] == 999 + 599
    with pytest.raises(PermissionError):
        create_order(req.model_copy(update={"payment": Payment(method="card", reference="FAIL-0000")}), PROFILE)
    with pytest.raises(ValueError):
        create_order(req.model_copy(update={"lines": [QuoteLine(product_id="P15", quantity=1)]}), PROFILE)


def test_advance_order_walks_the_timeline():
    req = OrderRequest(lines=[QuoteLine(product_id="P01", quantity=1)], customer=Customer(business_name="X"), payment=Payment(method="pay_later"))
    order = create_order(req, PROFILE)
    assert order["payment"]["status"] == "deferred"
    order = advance_order(order)
    assert order["current_status"] == "kyc_verified" and order["timeline"][1]["done_at"]
    order = advance_order(order, "activated")
    assert order["current_status"] == "activated" and all(s["done_at"] for s in order["timeline"])
    assert advance_order(order)["current_status"] == "activated"   # idempotent at the end


def test_seed_creates_demo_sessions_orders_and_handoffs_once():
    seed.seed_if_empty()
    seed.seed_if_empty()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == len(seed.DEMO_BUSINESSES)
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM handoff_leads").fetchone()[0] == 2
        statuses = {r[0] for r in conn.execute("SELECT current_status FROM orders")}
    assert statuses == {"activated", "technician_assigned", "ordered"}


def test_api_quote_and_order_flow():
    from app.main import app
    with TestClient(app) as c:
        s = c.post("/api/advisor/sessions", json={"seed_profile": PROFILE}).json()
        q = c.post("/api/quote", json={"session_id": s["session_id"], "lines": [{"product_id": "P01", "quantity": 1}, {"product_id": "P22", "quantity": 1}]}).json()
        assert q["pricing"]["monthly_total_inr"] == 1398
        o = c.post("/api/orders", json={"session_id": s["session_id"], "lines": [{"product_id": "P01", "quantity": 1}],
                                        "customer": {"business_name": "Test Store"}, "payment": {"method": "upi", "reference": "x@upi"}})
        assert o.status_code == 200 and o.json()["current_status"] == "ordered"
        declined = c.post("/api/orders", json={"session_id": s["session_id"], "lines": [{"product_id": "P01", "quantity": 1}],
                                               "customer": {"business_name": "Test Store"}, "payment": {"method": "card", "reference": "FAIL"}})
        assert declined.status_code == 402
        adv = c.post(f"/api/orders/{o.json()['id']}/advance", json={}).json()
        assert adv["current_status"] == "kyc_verified"
        assert c.get("/api/orders", params={"session_id": s["session_id"]}).json()[0]["id"] == o.json()["id"]
