"""
Tool definitions the advisor exposes to Claude (strict JSON schemas) and their implementations.

The LLM only ever: (1) updates the structured profile, (2) asks the rule engine for a recommendation,
(3) creates a handoff lead. It cannot invent products or prices because it has no other way to
produce them.
"""
from __future__ import annotations

from typing import Any

from .. import db
from ..engine import BusinessProfile, GstinStatus, Need, Recommendation, Segment, recommend
from .prompts import CITY_STATES, CITY_TIERS

NEED_VALUES = [n.value for n in Need]
PRODUCT_IDS = [f"P{i:02d}" for i in range(1, 26)]


# quantity name used in the tool -> field in the stored profile / engine model
QUANTITY_FIELDS = {
    "mobile_lines": "num_mobile_lines", "email_users": "num_users", "protected_devices": "num_devices",
    "cctv_cameras": "num_cameras", "billing_counters": "num_counters", "vehicles": "num_vehicles",
    "machines": "num_machines", "phone_channels": "num_channels",
}
QUANTITY_ITEMS = list(QUANTITY_FIELDS)


def _field(schema: dict, description: str) -> dict:
    # Plain (non-null) types: every profile field is optional, so "not learned" means "left out".
    # Strict tools allow at most 16 union-typed parameters, so nullable unions are avoided.
    return {**schema, "description": description}


UPDATE_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "business_type": _field({"type": "string"}, "Kind of business in English, e.g. 'Kirana store', 'Dental clinic', 'Restaurant chain', 'Textile unit'."),
        "city": _field({"type": "string"}, "City name in English."),
        "city_tier": _field({"type": "integer", "enum": [1, 2]}, "Only if the city is unknown to the system: 1 = big metro, 2 = other city."),
        "employee_count": _field({"type": "integer"}, "People working in the business, including the owner."),
        "num_sites": _field({"type": "integer"}, "Number of shops / branches / sites."),
        "has_gstin": _field({"type": "boolean"}, "Whether the business has a GST registration."),
        "gstin_status": _field({"type": "string", "enum": ["active", "cancelled", "suspended", "unknown"]}, "Only if the customer says their GSTIN is cancelled or suspended."),
        "has_udyam": _field({"type": "boolean"}, "Whether the business has a Udyam (MSME) registration."),
        "current_internet": _field({"type": "string"}, "What they use now: 'Mobile hotspot', 'Home broadband', 'Business broadband', 'Leased line', 'Mixed per site', 'None'."),
        "monthly_budget_inr": _field({"type": "integer"}, "Monthly budget or price limit in rupees. REQUIRED whenever the customer states one (e.g. 'budget is Rs 2000' -> 2000)."),
        "fibre_feasible": _field({"type": "boolean"}, "False only if the customer says fibre/wired broadband is not possible at their site."),
        "needs": _field({"type": "array", "items": {"type": "string", "enum": NEED_VALUES}}, "Needs the customer expressed, added to any already recorded."),
        "excluded_needs": _field({"type": "array", "items": {"type": "string", "enum": NEED_VALUES}}, "Needs the customer explicitly does NOT want (change of mind)."),
        "requested_products": _field({"type": "array", "items": {"type": "string", "enum": PRODUCT_IDS}}, "Specific catalogue products the customer asked for by description, e.g. '1 Gbps line' -> P03, 'leased line' -> P05."),
        "excluded_products": _field({"type": "array", "items": {"type": "string", "enum": PRODUCT_IDS}}, "Specific products the customer wants removed."),
        "quantities": _field({
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "item": {"type": "string", "enum": QUANTITY_ITEMS},
                    "count": {"type": "integer"},
                },
                "required": ["item", "count"],
            },
        }, "Quantities the customer stated: mobile_lines, email_users (if different from staff), protected_devices (if different "
           "from staff), cctv_cameras, billing_counters, vehicles, machines, phone_channels. Pass only the ones mentioned."),
        "contact_name": _field({"type": "string"}, "Customer's name if given."),
        "contact_phone": _field({"type": "string"}, "Callback number if the customer gives one for the handoff."),
        "preferred_language": _field({"type": "string"}, "Language the customer is writing in: 'Hindi', 'English', 'Hinglish', 'Marathi', ..."),
    },
    "required": [],
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "update_profile",
        "description": "Record facts the customer told you about their business and needs. Call it as soon as you learn something; pass only the fields you learned. Returns the full profile and which key facts are still missing.",
        "strict": True,
        "input_schema": UPDATE_PROFILE_SCHEMA,
    },
    {
        "name": "get_recommendation",
        "description": "Run the Accel Business rule engine on the current profile. Returns the eligible bundle with prices, setup fees, contract, reasons for each item, excluded items with reasons and alternatives, optional add-ons and warnings. This is the ONLY source of products and prices.",
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}, "required": []},
    },
    {
        "name": "create_handoff_lead",
        "description": "Hand the conversation to a local Accel Business salesperson or channel partner. Use when the customer hesitates, asks for a human, has needs the catalogue cannot cover, or the case needs a site survey.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "reason": {"type": "string", "enum": ["customer_hesitant", "wants_human", "needs_not_covered", "complex_case", "site_survey_needed", "other"]},
                "summary": {"type": "string", "description": "English summary for the salesperson: business, city, size, GSTIN, needs, what was quoted, why it did not close, suggested next step."},
                "callback": _field({"type": "string"}, "Preferred callback time and/or number if the customer gave one; empty string if not."),
            },
            "required": ["reason", "summary", "callback"],
        },
    },
]

KEY_FIELDS = ["business_type", "city", "employee_count", "has_gstin"]


# ---------------------------------------------------------------------------
# implementations
# ---------------------------------------------------------------------------
MIN_COUNTS = {"employee_count": 1, "num_sites": 1, "monthly_budget_inr": 0, "num_mobile_lines": 0, "num_users": 0,
              "num_devices": 0, "num_cameras": 0, "num_counters": 0, "num_vehicles": 0, "num_machines": 0, "num_channels": 0}


def apply_profile_update(profile: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge a tool call into the stored profile dict (lists are unioned, exclusions remove inclusions)."""
    p = dict(profile)
    update = dict(update)
    # the tool sends counts as a list of {item, count}; store them as flat num_* fields
    for q in update.pop("quantities", None) or []:
        field = QUANTITY_FIELDS.get(q.get("item"))
        if field and isinstance(q.get("count"), int):
            update[field] = q["count"]
    for key, value in update.items():
        if value is None:
            continue
        if key in ("needs", "excluded_needs", "requested_products", "excluded_products"):
            current = list(p.get(key, []))
            for v in value:
                if v not in current:
                    current.append(v)
            p[key] = current
        elif isinstance(value, int) and not isinstance(value, bool) and key in MIN_COUNTS:
            # strict tool schemas cannot carry numeric bounds, so enforce them here
            p[key] = max(MIN_COUNTS[key], value)
        else:
            p[key] = value
    # an explicit exclusion overrides an earlier inclusion, and a new inclusion overrides an earlier exclusion
    for inc, exc in (("needs", "excluded_needs"), ("requested_products", "excluded_products")):
        if inc in update and update[inc]:
            p[exc] = [v for v in p.get(exc, []) if v not in update[inc]]
        if exc in update and update[exc]:
            p[inc] = [v for v in p.get(inc, []) if v not in update[exc]]
    # city -> tier/state lookup from the dataset
    city = (p.get("city") or "").strip().lower()
    if city in CITY_TIERS:
        p["city_tier"] = CITY_TIERS[city]
        p["state"] = CITY_STATES[city]
    if p.get("gstin_status") in ("active", "cancelled", "suspended"):
        p["has_gstin"] = True   # "my GST got cancelled" means there is a GSTIN, just not a usable one
    if p.get("has_gstin") and not p.get("gstin_status"):
        p["gstin_status"] = "unknown"
    if p.get("has_gstin") is False:
        p["gstin_status"] = "unknown"
    return p


def missing_fields(profile: dict[str, Any]) -> list[str]:
    missing = [f for f in KEY_FIELDS if profile.get(f) in (None, "")]
    if profile.get("city") and not profile.get("city_tier"):
        missing.append("city_tier (city not recognised: ask if it is a big metro or a smaller city)")
    return missing


def to_business_profile(profile: dict[str, Any]) -> BusinessProfile:
    """Convert the loosely-typed stored profile into the engine's strict model."""
    fields = {k: v for k, v in profile.items() if k in BusinessProfile.model_fields and v is not None}
    if "gstin_status" in fields:
        fields["gstin_status"] = GstinStatus(fields["gstin_status"])
    if "segment" in fields and isinstance(fields["segment"], str):
        fields["segment"] = Segment(fields["segment"])
    for key in ("needs", "excluded_needs"):
        if key in fields:
            fields[key] = [Need(v) for v in fields[key] if v in NEED_VALUES]
    if not fields.get("has_gstin"):
        fields.pop("gstin_status", None)
    return BusinessProfile(**fields)


def price_summary(rec: Recommendation) -> str:
    """One sentence with every total already computed, for the model to quote verbatim."""
    pr = rec.pricing
    optional = sum(i.monthly_inr for i in rec.items if not i.is_core)
    without = f" (Rs {pr.monthly_total_inr - optional:,} without the optional items)" if optional else ""
    return (f"Monthly total Rs {pr.monthly_total_inr:,}{without}; one-time setup Rs {pr.setup_total_inr:,}; "
            f"{pr.contract_months}-month contract; installation in about {pr.expected_install_days} days.")


def recommendation_for_llm(rec: Recommendation) -> dict[str, Any]:
    """Compact, code-free view of the recommendation for the model to narrate."""
    return {
        "segment": rec.segment_label,
        "monthly_total_inr": rec.pricing.monthly_total_inr,
        "monthly_total_without_optional_inr": rec.pricing.monthly_total_inr - sum(i.monthly_inr for i in rec.items if not i.is_core),
        "price_summary": price_summary(rec),
        "setup_total_inr": rec.pricing.setup_total_inr,
        "contract_months": rec.pricing.contract_months,
        "expected_install_days": rec.pricing.expected_install_days,
        "budget_status": rec.pricing.budget_status.value,
        "budget_gap_inr": rec.pricing.budget_gap_inr,
        "items": [
            {"name": i.product_name, "quantity": i.quantity, "unit": i.unit, "unit_price_inr": i.unit_price_inr,
             "monthly_inr": i.monthly_inr,
             "setup_inr": i.setup_inr, "optional": not i.is_core, "why": " ".join(r.message for r in i.reasons)}
            for i in rec.items
        ],
        "excluded": [
            {"name": e.product_name, "why": " ".join(r.message for r in e.reasons), "alternative": e.alternative_product_name}
            for e in rec.excluded
        ],
        # quantity and unit matter: e.g. CCTV is quoted for 2 cameras, so monthly_inr is not a per-camera price
        "add_ons": [{"name": a.product_name, "quantity": a.default_quantity, "unit": a.unit, "unit_price_inr": a.unit_price_inr,
                     "monthly_inr": a.monthly_inr, "setup_inr": a.setup_inr, "what": a.description}
                    for a in rec.add_ons],
        "warnings": rec.warnings,
        "kyc_path": rec.kyc_path,
    }


def run_recommendation(profile: dict[str, Any]) -> Recommendation:
    return recommend(to_business_profile(profile))


def save_handoff(session: dict[str, Any], reason: str, summary: str, callback: str | None) -> str:
    profile = session["profile"]
    rec = session.get("recommendation")
    handoff_id = db.new_id("ho")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO handoff_leads (id, session_id, created_at, reason, summary, contact, city, state, segment, "
            "status, profile_json, recommendation_json, transcript_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (handoff_id, session["id"], db.now_iso(), reason, summary,
             callback or profile.get("contact_phone") or profile.get("contact_name"),
             profile.get("city"), profile.get("state"), (rec or {}).get("segment_label"),
             "open", db.dumps(profile), db.dumps(rec) if rec else None, db.dumps(session["transcript"])),
        )
    return handoff_id


REASON_TEXT = {
    "customer_hesitant": "Customer hesitated after seeing the bundle",
    "wants_human": "Customer asked to speak to a person",
    "needs_not_covered": "Needs not covered by the catalogue",
    "complex_case": "Complex case",
    "site_survey_needed": "Needs a site survey before quoting",
    "other": "Other",
}


def deterministic_summary(profile: dict[str, Any], rec: dict[str, Any] | None, reason: str) -> str:
    """Handoff summary written without the LLM (guided advisor and fallback)."""
    if profile.get("has_gstin"):
        gst = "GSTIN " + str(profile.get("gstin_status", "unknown"))
    else:
        gst = "Udyam only" if profile.get("has_udyam") else "no GSTIN or Udyam"
    parts = [
        f"{profile.get('business_type') or 'Business'} in {profile.get('city') or 'unknown city'},",
        f"{profile.get('employee_count', '?')} staff, {profile.get('num_sites', 1)} site(s), {gst}.",
        "Needs: " + (", ".join(profile.get("needs") or []) or "not stated") + ".",
    ]
    if profile.get("monthly_budget_inr"):
        parts.append(f"Budget Rs {profile['monthly_budget_inr']:,}/month.")
    if rec:
        names = ", ".join(f"{i['product_name']} x{i['quantity']}" for i in rec["items"])
        parts.append(f"Quoted Rs {rec['pricing']['monthly_total_inr']:,}/month + Rs {rec['pricing']['setup_total_inr']:,} setup: {names}.")
        if rec.get("excluded"):
            parts.append("Not eligible: " + ", ".join(e["product_name"] for e in rec["excluded"]) + ".")
    parts.append(f"Reason for handoff: {REASON_TEXT.get(reason, reason)}. Next step: call the customer and confirm the bundle.")
    return " ".join(parts)
