"""
KYC case lifecycle: consent -> upload (extract, discard image) -> checks -> decision.
Data minimisation: only extracted fields and check results are stored, with a retention date.
Identifiers are masked in every API response and never logged in full.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .. import db
from . import validators as V
from .checks import run_checks
from .extraction import extract_fields

log = logging.getLogger("kyc")
RETENTION_DAYS = 90          # extracted fields are purged 90 days after the case is created
NOTICE_VERSION = "2026-07-v1"

# DPDP consent purposes shown on the consent screen. Only `verification` is required.
PURPOSES = [
    {"key": "verification", "required": True, "title": "Verify my business and identity",
     "what": "GST / Udyam certificate, signatory ID and one address proof. We read the fields, check them against the GST and Udyam registries, and keep only the extracted results.",
     "why": "Required by telecom KYC rules before a connection can be activated.",
     "retention": "Extracted details for 90 days after the case closes; document images are deleted immediately after reading."},
    {"key": "service_updates", "required": False, "title": "Send order and installation updates on WhatsApp/SMS",
     "what": "Your mobile number and order status.", "why": "So you do not need to call to check progress.",
     "retention": "Until the order is activated plus 30 days."},
    {"key": "marketing", "required": False, "title": "Tell me about new offers",
     "what": "Business type, city and the products you bought.", "why": "Relevant offers only, max twice a month.",
     "retention": "Until you withdraw consent."},
    {"key": "partner_sharing", "required": False, "title": "Let a local Accel partner contact me for installation support",
     "what": "Business name, address and contact number.", "why": "Partners install and support in your area.",
     "retention": "Until the order is activated plus 30 days."},
]


# ---------------------------------------------------------------------------
# consent
# ---------------------------------------------------------------------------
def record_consent(session_id: str, purposes: dict[str, bool]) -> dict[str, Any]:
    if not purposes.get("verification"):
        raise ValueError("Verification consent is required to continue with KYC.")
    allowed = {p["key"] for p in PURPOSES}
    clean = {k: bool(v) for k, v in purposes.items() if k in allowed}
    consent = {"id": db.new_id("c"), "session_id": session_id, "created_at": db.now_iso(), "purposes": clean, "notice_version": NOTICE_VERSION}
    with db.connect() as conn:
        conn.execute("INSERT INTO consents (id, session_id, created_at, purposes_json, notice_version) VALUES (?,?,?,?,?)",
                     (consent["id"], session_id, consent["created_at"], db.dumps(clean), NOTICE_VERSION))
    return consent


def has_verification_consent(session_id: str) -> bool:
    with db.connect() as conn:
        rows = conn.execute("SELECT purposes_json FROM consents WHERE session_id = ? ORDER BY created_at DESC", (session_id,)).fetchall()
    return any(db.loads(r["purposes_json"]).get("verification") for r in rows)


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------
def create_case(session_id: str | None, kyc_path: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    case = {
        "id": db.new_id("kyc"), "session_id": session_id, "created_at": now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"), "path": kyc_path, "status": "in_progress",
        "documents": {}, "checks": {}, "retention_until": (now + timedelta(days=RETENTION_DAYS)).date().isoformat(),
    }
    _insert(case)
    return case


def _insert(case: dict[str, Any]) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO kyc_cases (id, session_id, created_at, updated_at, path, status, documents_json, checks_json, retention_until) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (case["id"], case["session_id"], case["created_at"], case["updated_at"], case["path"], case["status"],
                      db.dumps(case["documents"]), db.dumps(case["checks"]), case["retention_until"]))


def _save(case: dict[str, Any]) -> None:
    case["updated_at"] = db.now_iso()
    with db.connect() as conn:
        conn.execute("UPDATE kyc_cases SET updated_at=?, path=?, status=?, documents_json=?, checks_json=? WHERE id=?",
                     (case["updated_at"], case["path"], case["status"], db.dumps(case["documents"]), db.dumps(case["checks"]), case["id"]))


def get_case(case_id: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM kyc_cases WHERE id = ?", (case_id,)).fetchone()
    return db.row_to_dict(row)


def add_document(case: dict[str, Any], doc_type: str, image_bytes: bytes) -> dict[str, Any]:
    """Extract fields with Claude vision, store the fields (not the image), re-run checks.
    Without an API key, a known specimen image falls back to the hand-read golden fields so the
    demo still runs; any other image raises a clear error."""
    import os

    from . import specimens

    if os.environ.get("ANTHROPIC_API_KEY"):
        fields = extract_fields(doc_type, image_bytes)
    else:
        fields = specimens.fixture_for_image(image_bytes)
        if fields is None:
            raise RuntimeError("Document reading needs ANTHROPIC_API_KEY (set it in .env). Sample documents still work without it.")
    log.info("kyc case %s: read %s (confidence %s, legibility %s)", case["id"], doc_type, fields.get("confidence"), fields.get("legibility"))
    return add_extracted(case, doc_type, fields)


def add_extracted(case: dict[str, Any], doc_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Store already-extracted fields (used by tests and the specimen runner) and re-run checks."""
    case["documents"][doc_type] = fields
    case["checks"] = run_checks(case["documents"], case["path"])
    case["status"] = case["checks"]["overall"] if _complete(case) else "in_progress"
    _save(case)
    return case


def finalise(case: dict[str, Any]) -> dict[str, Any]:
    case["checks"] = run_checks(case["documents"], case["path"])
    case["status"] = case["checks"]["overall"]
    _save(case)
    return case


def _complete(case: dict[str, Any]) -> bool:
    from .checks import REQUIRED_BY_PATH
    return all(d in case["documents"] for d in REQUIRED_BY_PATH.get(case["path"], []))


def purge_expired(now: datetime | None = None) -> int:
    """Delete extracted fields past their retention date (keeps the decision, drops the personal data)."""
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    with db.connect() as conn:
        cur = conn.execute("UPDATE kyc_cases SET documents_json = '{}' WHERE retention_until < ? AND documents_json != '{}'", (today,))
        return cur.rowcount


# ---------------------------------------------------------------------------
# presentation: masked view for the UI
# ---------------------------------------------------------------------------
MASK_RULES = {
    "gstin": lambda v: V.mask(v, 2, 3), "udyam_number": V.mask_udyam, "id_number": lambda v: V.mask(v, 7, 2),
    "consumer_number": lambda v: V.mask(v, 0, 4),
}


def masked_view(case: dict[str, Any]) -> dict[str, Any]:
    docs = {}
    for doc_type, fields in (case.get("documents") or {}).items():
        shown = {k: v for k, v in fields.items() if not k.startswith("_")}
        for key, fn in MASK_RULES.items():
            if shown.get(key):
                shown[key] = fn(shown[key])
        docs[doc_type] = shown
    return {
        "id": case["id"], "session_id": case.get("session_id"), "path": case["path"], "status": case["status"],
        "created_at": case["created_at"], "retention_until": case.get("retention_until"),
        "documents": docs, "checks": case.get("checks") or {},
        "required_documents": __import__("app.kyc.checks", fromlist=["REQUIRED_BY_PATH"]).REQUIRED_BY_PATH.get(case["path"], []),
    }
