"""
Orders: mock checkout and the activation timeline the tracker shows.

Timeline (expected dates come from the catalogue's typical_install_days):
  ordered -> KYC verified -> technician assigned -> installation scheduled -> activated
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from . import db
from .quote import QuoteLine, build_quote

STATUSES = ["ordered", "kyc_verified", "technician_assigned", "installation_scheduled", "activated"]
LABELS = {
    "ordered": "Order placed",
    "kyc_verified": "KYC verified",
    "technician_assigned": "Technician assigned",
    "installation_scheduled": "Installation scheduled",
    "activated": "Activated",
}


class Customer(BaseModel):
    business_name: str = Field(min_length=1)
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None


class Payment(BaseModel):
    method: str = Field(pattern="^(upi|card|netbanking|pay_later)$")
    reference: Optional[str] = None   # UPI id / last 4 digits / bank name (mock)


class OrderRequest(BaseModel):
    session_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None
    lines: list[QuoteLine]
    customer: Customer
    payment: Payment


def build_timeline(start: datetime, install_days: int) -> list[dict[str, Any]]:
    """Expected dates for each step. KYC is expected same day (digital), activation at install_days."""
    install_days = max(install_days, 2)
    offsets = {
        "ordered": 0,
        "kyc_verified": 0,
        "technician_assigned": 1,
        "installation_scheduled": max(1, math.ceil(install_days * 0.5)),
        "activated": install_days,
    }
    return [
        {"status": s, "label": LABELS[s], "expected_at": (start + timedelta(days=offsets[s])).date().isoformat(),
         "done_at": start.isoformat(timespec="seconds") if s == "ordered" else None}
        for s in STATUSES
    ]


def mock_payment(payment: Payment, amount_inr: int) -> dict[str, Any]:
    """Pretend to charge. A reference containing 'FAIL' simulates a declined payment for the demo."""
    ref = (payment.reference or "").upper()
    if "FAIL" in ref:
        return {"status": "failed", "method": payment.method, "amount_inr": amount_inr,
                "message": "Payment was declined by the bank. No money was taken. Try another method."}
    if payment.method == "pay_later":
        return {"status": "deferred", "method": payment.method, "amount_inr": amount_inr,
                "message": "Setup fee will be added to your first bill."}
    return {"status": "paid", "method": payment.method, "amount_inr": amount_inr,
            "transaction_id": "TXN" + db.new_id("")[1:].upper(), "message": "Payment successful."}


def create_order(req: OrderRequest, profile: dict[str, Any], kyc_case_id: str | None = None) -> dict[str, Any]:
    quote = build_quote(profile, req.lines)
    blocking = [i for i in quote.issues if i.severity == "blocking"]
    if blocking or not quote.items:
        raise ValueError("Some items are not available for this business: " + "; ".join(i.message for i in blocking))
    payment = mock_payment(req.payment, quote.pricing.setup_total_inr)
    if payment["status"] == "failed":
        raise PermissionError(payment["message"])

    now = datetime.now(timezone.utc)
    order = {
        "id": db.new_id("ord"), "session_id": req.session_id, "kyc_case_id": kyc_case_id,
        "created_at": now.isoformat(timespec="seconds"),
        "business_name": req.customer.business_name, "city": req.customer.city or profile.get("city"),
        "items": [i.model_dump(mode="json") for i in quote.items],
        "pricing": quote.pricing.model_dump(mode="json"),
        "payment": payment | {"customer": req.customer.model_dump()},
        "timeline": build_timeline(now, quote.pricing.expected_install_days),
        "current_status": "ordered",
        "kyc_path": quote.kyc_path,
    }
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO orders (id, session_id, kyc_case_id, created_at, business_name, city, items_json, pricing_json, "
            "payment_json, timeline_json, current_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (order["id"], order["session_id"], kyc_case_id, order["created_at"], order["business_name"], order["city"],
             db.dumps(order["items"]), db.dumps(order["pricing"]), db.dumps(order["payment"]),
             db.dumps(order["timeline"]), order["current_status"]))
    return order


def get_order(order_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return db.row_to_dict(row)


def list_orders(session_id: str | None = None) -> list[dict[str, Any]]:
    with db.connect() as conn:
        if session_id:
            rows = conn.execute("SELECT * FROM orders WHERE session_id = ? ORDER BY created_at DESC", (session_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return [db.row_to_dict(r) for r in rows]


def advance_order(order: dict[str, Any], to_status: str | None = None) -> dict[str, Any]:
    """Move the order to the next status (or a given one), stamping done_at. Used by the demo simulator."""
    idx = STATUSES.index(order["current_status"])
    target = STATUSES.index(to_status) if to_status else min(idx + 1, len(STATUSES) - 1)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for step in order["timeline"]:
        if STATUSES.index(step["status"]) <= target and not step["done_at"]:
            step["done_at"] = now
    order["current_status"] = STATUSES[target]
    with db.connect() as conn:
        conn.execute("UPDATE orders SET timeline_json = ?, current_status = ?, kyc_case_id = COALESCE(?, kyc_case_id) WHERE id = ?",
                     (db.dumps(order["timeline"]), order["current_status"], order.get("kyc_case_id"), order["id"]))
    return order
