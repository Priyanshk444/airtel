"""FastAPI application for Project Udyam Digital (Accel Business prototype)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, orders, seed
from .kyc import service as kyc, specimens
from .advisor import service as advisor
from .engine import BusinessProfile, Recommendation, load_catalogue, recommend
from .quote import QuoteRequest, QuoteResponse, build_quote

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    seed.seed_if_empty()
    yield


app = FastAPI(title="Accel Business - Udyam Digital", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm_available": advisor.llm_available(), "advisor_model": advisor.MODEL}


# --- catalogue & engine ---------------------------------------------------------------------
@app.get("/api/catalogue")
def catalogue() -> list[dict[str, Any]]:
    return [p.model_dump() for p in load_catalogue().values()]


@app.post("/api/recommend", response_model=Recommendation)
def recommend_endpoint(profile: BusinessProfile) -> Recommendation:
    return recommend(profile)


# --- advisor ---------------------------------------------------------------------------------
class NewSession(BaseModel):
    assisted_by: Optional[str] = None
    seed_profile: Optional[dict[str, Any]] = None


class UserMessage(BaseModel):
    message: str


@app.post("/api/advisor/sessions")
def new_session(body: NewSession | None = None) -> dict[str, Any]:
    body = body or NewSession()
    session = advisor.create_session(assisted_by=body.assisted_by, seed_profile=body.seed_profile)
    return advisor.state_for_ui(session, "")


@app.get("/api/advisor/sessions")
def list_sessions() -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT id, created_at, stage, profile_json, assisted_by FROM sessions ORDER BY created_at DESC LIMIT 50").fetchall()
    return [db.row_to_dict(r) for r in rows]


@app.get("/api/advisor/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = _session_or_404(session_id)
    return advisor.state_for_ui(session, "")


@app.post("/api/advisor/sessions/{session_id}/messages")
def post_message(session_id: str, body: UserMessage) -> dict[str, Any]:
    session = _session_or_404(session_id)
    try:
        return advisor.handle_message(session, body.message)
    except advisor.LLMUnavailable as exc:   # UI switches to the guided advisor on this code
        raise HTTPException(503, f"llm_unavailable: {exc}") from exc
    except Exception as exc:  # surface a clean error to the UI, keep the session intact
        logging.getLogger("advisor").exception("advisor turn failed")
        raise HTTPException(502, f"advisor error: {type(exc).__name__}: {exc}") from exc


class GuidedAnswers(BaseModel):
    answers: dict[str, Any]
    summary_line: Optional[str] = None


class GuidedHandoff(BaseModel):
    reason: str = "wants_human"
    callback: Optional[str] = None


@app.post("/api/advisor/sessions/{session_id}/guided")
def guided_answers(session_id: str, body: GuidedAnswers) -> dict[str, Any]:
    """Tap-to-answer advisor (no LLM): set the profile from button answers and run the rule engine."""
    session = _session_or_404(session_id)
    try:
        return advisor.apply_guided_profile(session, body.answers, body.summary_line)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"invalid answers: {exc}") from exc


@app.post("/api/advisor/sessions/{session_id}/handoff")
def request_handoff(session_id: str, body: GuidedHandoff) -> dict[str, Any]:
    """'Talk to a person' button: creates a handoff lead with a deterministic summary."""
    return advisor.guided_handoff(_session_or_404(session_id), body.reason, body.callback)


def _session_or_404(session_id: str) -> dict[str, Any]:
    session = advisor.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    return session


def _profile_for(session_id: str | None, profile: dict[str, Any] | None) -> dict[str, Any]:
    if session_id:
        return _session_or_404(session_id)["profile"]
    if profile is not None:
        return profile
    raise HTTPException(400, "session_id or profile is required")


# --- quote & checkout ------------------------------------------------------------------------
@app.post("/api/quote", response_model=QuoteResponse)
def quote(body: QuoteRequest) -> QuoteResponse:
    return build_quote(_profile_for(body.session_id, body.profile), body.lines)


@app.post("/api/orders")
def place_order(body: orders.OrderRequest) -> dict[str, Any]:
    profile = _profile_for(body.session_id, body.profile)
    try:
        return orders.create_order(body, profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PermissionError as exc:   # mock payment declined
        raise HTTPException(402, str(exc)) from exc


@app.get("/api/orders")
def list_orders(session_id: Optional[str] = None) -> list[dict[str, Any]]:
    return orders.list_orders(session_id)


@app.get("/api/orders/{order_id}")
def get_order(order_id: str) -> dict[str, Any]:
    order = orders.get_order(order_id)
    if not order:
        raise HTTPException(404, "order not found")
    return order


class Advance(BaseModel):
    to_status: Optional[str] = None


@app.post("/api/orders/{order_id}/advance")
def advance(order_id: str, body: Advance | None = None) -> dict[str, Any]:
    """Demo simulator: move an order to its next status."""
    order = orders.get_order(order_id)
    if not order:
        raise HTTPException(404, "order not found")
    to_status = (body or Advance()).to_status
    if to_status and to_status not in orders.STATUSES:
        raise HTTPException(400, f"unknown status {to_status}")
    return orders.advance_order(order, to_status)


# --- handoff leads (back office) -------------------------------------------------------------
@app.get("/api/handoffs")
def list_handoffs(state: Optional[str] = None, city: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM handoff_leads WHERE 1=1"
    params: list[Any] = []
    if state:
        query += " AND state = ?"; params.append(state)
    if city:
        query += " AND city = ?"; params.append(city)
    if status:
        query += " AND status = ?"; params.append(status)
    query += " ORDER BY created_at DESC"
    with db.connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [db.row_to_dict(r) for r in rows]


class HandoffStatus(BaseModel):
    status: str


@app.patch("/api/handoffs/{handoff_id}")
def update_handoff(handoff_id: str, body: HandoffStatus) -> dict[str, Any]:
    with db.connect() as conn:
        conn.execute("UPDATE handoff_leads SET status = ? WHERE id = ?", (body.status, handoff_id))
        row = conn.execute("SELECT * FROM handoff_leads WHERE id = ?", (handoff_id,)).fetchone()
    if not row:
        raise HTTPException(404, "handoff not found")
    return db.row_to_dict(row)


# --- Smart KYC -------------------------------------------------------------------------------
class ConsentBody(BaseModel):
    session_id: str
    purposes: dict[str, bool]


class NewCase(BaseModel):
    session_id: str
    order_id: Optional[str] = None
    kyc_path: Optional[str] = None   # defaults to the path the engine decided for the session


class SpecimenDoc(BaseModel):
    applicant: str
    doc_type: str


@app.get("/api/kyc/consent/purposes")
def consent_purposes() -> list[dict[str, Any]]:
    return kyc.PURPOSES


@app.post("/api/kyc/consent")
def give_consent(body: ConsentBody) -> dict[str, Any]:
    try:
        return kyc.record_consent(body.session_id, body.purposes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/kyc/cases")
def new_case(body: NewCase) -> dict[str, Any]:
    if not kyc.has_verification_consent(body.session_id):
        raise HTTPException(403, "Consent for verification is required before uploading documents.")
    session = _session_or_404(body.session_id)
    path = body.kyc_path or (session.get("recommendation") or {}).get("kyc_path") or "gstin"
    case = kyc.create_case(body.session_id, path)
    if body.order_id:
        with db.connect() as conn:
            conn.execute("UPDATE orders SET kyc_case_id = ? WHERE id = ?", (case["id"], body.order_id))
    return kyc.masked_view(case)


@app.get("/api/kyc/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    return kyc.masked_view(_case_or_404(case_id))


@app.post("/api/kyc/cases/{case_id}/documents")
async def upload_document(case_id: str, doc_type: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    """Multipart upload. The image is read into memory, sent to the reader, and discarded."""
    case = _case_or_404(case_id)
    if doc_type not in specimens.DOC_TYPES:
        raise HTTPException(400, f"doc_type must be one of {specimens.DOC_TYPES}")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 15 MB).")
    try:
        case = kyc.add_document(case, doc_type, data)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    _sync_order(case)
    return kyc.masked_view(case)


@app.post("/api/kyc/cases/{case_id}/documents/specimen")
def upload_specimen(case_id: str, body: SpecimenDoc) -> dict[str, Any]:
    """Demo helper: 'upload' one of the 12 sample applicants' documents from data/kyc_documents."""
    case = _case_or_404(case_id)
    path = specimens.specimen_path(body.applicant.upper(), body.doc_type)
    if not path:
        raise HTTPException(404, "no such specimen document")
    try:
        case = kyc.add_document(case, body.doc_type, path.read_bytes())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    _sync_order(case)
    return kyc.masked_view(case)


@app.get("/api/kyc/specimens")
def list_specimens() -> list[dict[str, Any]]:
    return specimens.applicants()


def _case_or_404(case_id: str) -> dict[str, Any]:
    case = kyc.get_case(case_id)
    if not case:
        raise HTTPException(404, "KYC case not found")
    return case


def _sync_order(case: dict[str, Any]) -> None:
    """When a case is verified, move its order to 'KYC verified' so the tracker reflects it."""
    if case["status"] != "verified":
        return
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM orders WHERE kyc_case_id = ?", (case["id"],)).fetchone()
    if row:
        order = orders.get_order(row["id"])
        if order and order["current_status"] == "ordered":
            orders.advance_order(order, "kyc_verified")


# --- partner back office: propensity, assisted sessions ------------------------------------
from . import propensity  # noqa: E402


@app.get("/api/propensity/model")
def propensity_model() -> dict[str, Any]:
    m = propensity.get_model()
    return {"metrics": m.metrics, "top_factors": m.factors(), "features_used": [propensity.FRIENDLY[f] for f in propensity.CATEGORICAL + propensity.NUMERIC]}


@app.get("/api/propensity/leads")
def propensity_leads(state: Optional[str] = None, city: Optional[str] = None, segment: Optional[str] = None, limit: int = 25) -> list[dict[str, Any]]:
    return propensity.get_model().rank(state=state, city=city, segment=segment, limit=min(limit, 200))


@app.get("/api/partner/territories")
def territories() -> dict[str, list[str]]:
    df = propensity.get_model().leads
    return {s: sorted(df[df.state == s].city.unique().tolist()) for s in sorted(df.state.unique())}


@app.get("/api/partner/sessions")
def partner_sessions(assisted_by: Optional[str] = None) -> list[dict[str, Any]]:
    query = "SELECT id, created_at, updated_at, stage, assisted_by, profile_json, recommendation_json, handoff_id FROM sessions"
    params: list[Any] = []
    if assisted_by:
        query += " WHERE assisted_by = ?"; params.append(assisted_by)
    query += " ORDER BY updated_at DESC LIMIT 100"
    with db.connect() as conn:
        rows = [db.row_to_dict(r) for r in conn.execute(query, params).fetchall()]
    for r in rows:
        rec = r.pop("recommendation", None) or {}
        r["monthly_total_inr"] = (rec.get("pricing") or {}).get("monthly_total_inr")
        r["segment_label"] = rec.get("segment_label")
        with db.connect() as conn:
            o = conn.execute("SELECT id, current_status FROM orders WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (r["id"],)).fetchone()
        r["order"] = dict(o) if o else None
    return rows
