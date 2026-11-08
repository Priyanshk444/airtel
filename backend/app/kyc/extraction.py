"""
Document field extraction with Claude vision (default claude-haiku-5-5, override with KYC_MODEL), using structured output so the
response is always valid JSON matching our schema. Images are downscaled before sending and are
never written to disk or the database.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from typing import Any

import anthropic
from PIL import Image

MODEL = os.environ.get("KYC_MODEL", "claude-haiku-5-5")
MAX_SIDE = 1600   # px; the specimens are 1240x1754, so this only shrinks oversized phone photos

COMMON = {
    "legibility": {"type": "string", "enum": ["clear", "skewed", "blurred", "partial", "unreadable"],
                   "description": "Overall legibility of the document image."},
    "confidence": {"type": "number", "description": "Between 0 and 1: your confidence that every field was read exactly."},
    "notes": {"type": ["string", "null"], "description": "Anything odd: blank fields, corrections, mismatches inside the document."},
}


def _schema(props: dict[str, Any]) -> dict[str, Any]:
    all_props = {**props, **COMMON}
    return {"type": "object", "properties": all_props, "required": list(all_props), "additionalProperties": False}


S = {"type": ["string", "null"]}
SCHEMAS: dict[str, dict[str, Any]] = {
    "gst_certificate": _schema({
        "gstin": {**S, "description": "15-character GSTIN exactly as printed, no spaces."},
        "legal_name": S, "trade_name": S, "constitution": S,
        "address": {**S, "description": "Full principal place of business on one line; join words broken across lines."},
        "date_of_liability": {**S, "description": "YYYY-MM-DD"}, "type_of_registration": S,
    }),
    "udyam_certificate": _schema({
        "udyam_number": {**S, "description": "Exactly as printed, e.g. UDYAM-MH-00-1234567. null if the field is blank."},
        "enterprise_name": S, "major_activity": S, "city": S, "state": S,
        "date_of_registration": {**S, "description": "YYYY-MM-DD"},
    }),
    "signatory_id": _schema({
        "name": S, "designation": S, "business_name": {**S, "description": "The 'For business' value."},
        "id_number": S, "valid_till": {**S, "description": "YYYY-MM-DD"},
    }),
    "address_proof": _schema({
        "document_kind": {**S, "description": "e.g. electricity bill, telephone bill, rent agreement"},
        "consumer_number": S, "billed_to": S,
        "supply_address": {**S, "description": "Full address on one line; join words broken across lines."},
        "bill_date": {**S, "description": "YYYY-MM-DD"},
    }),
}

PROMPT = (
    "You are reading a KYC document for a telecom business connection in India. Extract the fields exactly as printed. "
    "Join words that are broken across two lines (e.g. 'A' + 'ndhra Pradesh' -> 'Andhra Pradesh'). "
    "If a field is blank, missing or unreadable, return null for it - never guess or fill from context. "
    "Dates as YYYY-MM-DD. Report legibility honestly (skewed, blurred, partial) and lower your confidence when characters "
    "like O/0, I/1 or S/5 are ambiguous. Ignore watermarks such as 'SYNTHETIC SPECIMEN'."
)

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=2, timeout=90.0)
    return _client


def prepare_image(data: bytes) -> tuple[str, str]:
    """Downscale, convert to PNG, return (base64, sha256 of the original). Original bytes are not kept."""
    digest = hashlib.sha256(data).hexdigest()
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), digest


def extract_fields(doc_type: str, image_bytes: bytes) -> dict[str, Any]:
    """Call Claude vision once and return the schema-shaped dict plus usage info."""
    if doc_type not in SCHEMAS:
        raise ValueError(f"unknown document type {doc_type}")
    b64, digest = prepare_image(image_bytes)
    response = client().messages.create(
        model=MODEL,
        max_tokens=2048,   # thinking counts toward max_tokens on Haiku 5.5
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMAS[doc_type]}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": f"{PROMPT}\n\nDocument type: {doc_type.replace('_', ' ')}."},
            ],
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The document reader declined to process this image.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The document reader ran out of room; try again.")
    text = next((b.text for b in response.content if b.type == "text"), "{}")
    fields = json.loads(text)
    # structured outputs do not enforce numeric bounds, so clamp here
    if isinstance(fields.get("confidence"), (int, float)):
        fields["confidence"] = min(1.0, max(0.0, float(fields["confidence"])))
    fields["_meta"] = {
        "sha256": digest, "model": MODEL,
        "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
    }
    return fields
