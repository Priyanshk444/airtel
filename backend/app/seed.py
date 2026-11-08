"""
Demo seed: a few fictional businesses taken from smb_leads.csv so the demo has data on first start.
Runs once when the database is empty. No LLM calls: recommendations come from the rule engine.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import db
from .advisor import service, tools as T
from .orders import STATUSES, build_timeline
from .quote import QuoteLine, build_quote

log = logging.getLogger("seed")

# (business, profile facts, needs) - all names and identifiers are from the synthetic pack
DEMO_BUSINESSES = [
    {"name": "Saffron Bakers", "profile": {"business_type": "Bakery", "city": "Ludhiana", "employee_count": 3, "num_sites": 1,
                                           "has_gstin": True, "gstin_status": "active", "has_udyam": False,
                                           "needs": ["internet", "mobile_lines", "pos_billing"], "num_mobile_lines": 2, "contact_name": "Sneha Rao"},
     "order_status": "activated", "days_ago": 20},
    {"name": "Balaji Dental Care LLP", "profile": {"business_type": "Dental clinic", "city": "Kochi", "employee_count": 20, "num_sites": 1,
                                                   "has_gstin": True, "gstin_status": "active", "has_udyam": True,
                                                   "needs": ["internet", "cloud_telephony", "email"], "contact_name": "Prakash Shah"},
     "order_status": "technician_assigned", "days_ago": 3},
    {"name": "Star Electronics", "profile": {"business_type": "Electronics retail chain", "city": "Chennai", "employee_count": 55, "num_sites": 9,
                                             "has_gstin": True, "gstin_status": "active", "has_udyam": True,
                                             "needs": ["internet", "backup_internet", "cctv", "pos_billing"], "contact_name": "Joseph Joshi"},
     "order_status": "ordered", "days_ago": 0},
    {"name": "Lakshmi General Store", "profile": {"business_type": "Kirana store", "city": "Nashik", "employee_count": 2, "num_sites": 1,
                                                  "has_gstin": False, "has_udyam": True, "needs": ["internet", "mobile_lines"]},
     "order_status": None, "days_ago": 1},
    {"name": "Evergreen Sweets", "profile": {"business_type": "Sweet shop", "city": "Kochi", "employee_count": 4, "num_sites": 1,
                                             "has_gstin": True, "gstin_status": "cancelled", "has_udyam": False,
                                             "needs": ["internet", "whatsapp"]},
     "order_status": None, "days_ago": 1},
]

DEMO_HANDOFFS = [
    {"name": "Amrit Auto Components", "city": "Delhi", "state": "Delhi", "segment": "Small manufacturers", "reason": "site_survey_needed",
     "summary": "Auto-parts unit in Delhi, 75 staff, GSTIN active. Wants a dedicated leased line, email for all staff and machine monitoring on 10 machines. "
                "Quoted Rs 22,000+/month. Needs a site survey for the leased line before committing. Best next step: partner visit this week."},
    {"name": "Zenith Diagnostics", "city": "Nagpur", "state": "Maharashtra", "segment": "Professional offices", "reason": "customer_hesitant",
     "summary": "Diagnostic lab in Nagpur, 13 staff, GSTIN active. Quoted fibre 300 + email + backup at about Rs 6,000/month. "
                "Owner wants to compare with current provider (Accel home plan) and asked for a call-back next Tuesday after 4 pm."},
]


def seed_if_empty() -> None:
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if n:
        return
    log.info("seeding demo data")
    for biz in DEMO_BUSINESSES:
        profile = T.apply_profile_update({}, biz["profile"])
        profile["business_name"] = biz["name"]
        session = service.create_session(seed_profile=profile)
        rec = T.run_recommendation(profile)
        session["recommendation"] = rec.model_dump(mode="json")
        session["stage"] = "recommended"
        session["transcript"] = [{"role": "assistant", "text": f"(Demo business: {biz['name']}. Profile pre-filled.)"}]
        service._save(session)
        if biz["order_status"]:
            _seed_order(session, biz)
    for h in DEMO_HANDOFFS:
        hid = db.new_id("ho")
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO handoff_leads (id, session_id, created_at, reason, summary, contact, city, state, segment, status, "
                "profile_json, recommendation_json, transcript_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (hid, "seed", db.now_iso(), h["reason"], h["summary"], h["name"], h["city"], h["state"], h["segment"], "open",
                 db.dumps({"business_name": h["name"], "city": h["city"]}), None, db.dumps([])))


def _seed_order(session: dict, biz: dict) -> None:
    rec = session["recommendation"]
    lines = [QuoteLine(product_id=i["product_id"], quantity=i["quantity"]) for i in rec["items"]]
    quote = build_quote(session["profile"], lines)
    created = datetime.now(timezone.utc) - timedelta(days=biz["days_ago"])
    timeline = build_timeline(created, quote.pricing.expected_install_days)
    target = STATUSES.index(biz["order_status"])
    for step in timeline:
        if STATUSES.index(step["status"]) <= target:
            step["done_at"] = (created + timedelta(days=STATUSES.index(step["status"]))).isoformat(timespec="seconds")
    order_id = db.new_id("ord")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO orders (id, session_id, kyc_case_id, created_at, business_name, city, items_json, pricing_json, payment_json, "
            "timeline_json, current_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (order_id, session["id"], None, created.isoformat(timespec="seconds"), biz["name"], session["profile"].get("city"),
             db.dumps([i.model_dump(mode="json") for i in quote.items]), db.dumps(quote.pricing.model_dump(mode="json")),
             db.dumps({"status": "paid", "method": "upi", "amount_inr": quote.pricing.setup_total_inr, "customer": {"business_name": biz["name"]}}),
             db.dumps(timeline), biz["order_status"]))
