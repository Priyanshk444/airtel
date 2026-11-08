"""
Specimen helpers: the 12 applicants in data/kyc_documents and the hand-read golden fields.
Used by the demo ("use sample document"), by tests, and as a fallback reader when no API key is set.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from ..engine.catalogue import data_dir

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "kyc_golden.json"
DOC_TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]


@lru_cache(maxsize=1)
def golden() -> dict[str, dict[str, dict]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def specimen_path(applicant: str, doc_type: str) -> Path | None:
    p = data_dir() / "kyc_documents" / f"{applicant}_{doc_type}.png"
    return p if p.exists() else None


def applicants() -> list[dict]:
    out = []
    for k in sorted(golden()):
        docs = [d for d in DOC_TYPES if specimen_path(k, d)]
        name = golden()[k].get("gst_certificate", {}).get("trade_name") or golden()[k].get("udyam_certificate", {}).get("enterprise_name")
        out.append({"applicant": k, "business_name": name, "documents": docs})
    return out


@lru_cache(maxsize=1)
def hash_index() -> dict[str, tuple[str, str]]:
    """sha256 of every specimen image -> (applicant, doc_type)."""
    idx = {}
    for k in golden():
        for d in DOC_TYPES:
            p = specimen_path(k, d)
            if p:
                idx[hashlib.sha256(p.read_bytes()).hexdigest()] = (k, d)
    return idx


def fixture_for_image(image_bytes: bytes) -> dict | None:
    """If the uploaded image is one of the specimens, return its golden fields (fallback without an API key)."""
    hit = hash_index().get(hashlib.sha256(image_bytes).hexdigest())
    if not hit:
        return None
    applicant, doc_type = hit
    fields = dict(golden()[applicant][doc_type])
    fields["_meta"] = {"source": "golden_fixture", "applicant": applicant, "model": None}
    return fields
