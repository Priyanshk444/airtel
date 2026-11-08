"""Smart KYC: validators, checks on the 12 golden specimens, consent, masking, retention, API flow."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.kyc import checks as C, service as S, specimens, validators as V

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "kyc_golden.json").read_text(encoding="utf-8"))
GOLDEN = {k: v for k, v in GOLDEN.items() if not k.startswith("_")}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("UDYAM_DB_PATH", str(tmp_path / "kyc.sqlite"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db.init_db()


# ---------------------------------------------------------------------------
# validators
# ---------------------------------------------------------------------------
def test_gstin_checksum_and_repair():
    assert V.gstin_checksum_ok("37IHKXV5167L1ZS")
    assert not V.gstin_checksum_ok("37IHKXV5167L1ZX")
    assert not V.gstin_checksum_ok("19E0GXH4115Y1ZL")              # digit in a letter slot
    assert V.repair_gstin("19E0GXH4115Y1ZL") == ("19EOGXH4115Y1ZL", ["position 4: 0 -> O"])
    assert V.repair_gstin("24X0RXG9365M1Z3")[0] == "24XORXG9365M1Z3"
    assert V.repair_gstin("27PZSXS1936D1ZH")[0] == "27PZSXS1936O1ZH"   # blurred D is an O
    assert V.repair_gstin("08YKZXS8189L1Z0")[0] is None               # genuinely invalid
    assert V.repair_gstin("abc") == (None, [])


def test_state_codes_pan_and_udyam_format():
    assert V.gstin_state("37ABCDE1234F1Z5") == "Andhra Pradesh"
    assert V.pan_from_gstin("37IHKXV5167L1ZS") == "IHKXV5167L"
    assert V.udyam_parts("UDYAM-MH-00-9516696")["state"] == "Maharashtra"
    assert V.udyam_parts("UDYAM-MH-9516696") is None


def test_name_and_address_similarity():
    assert V.name_similarity("Vindhya Tours & Travels", "Vindhya Tours and Travels") >= 95
    assert V.name_similarity("Neelgiri Physio Clinic", "Shri Physio Clinic") < 90
    assert V.address_similarity("Shop/Unit 1, Tech Park Road, Visakhapatnam, A ndhra Pradesh - 118383",
                                "Shop/Unit 1, Tech Park Road, Visakhapatnam, Andhra Pradesh - 118383") >= 95
    assert V.pincode("Shop/Unit 38, Civil Lines, Kochi, Kerala - 75 2083") == "752083"
    assert V.proprietor_from_legal_name("Neha Kaur (Prop. Vindhya Tours & Travels)") == ("Neha Kaur", "Vindhya Tours & Travels")


def test_dates_and_masking():
    assert V.days_old("2026-06-26") == 19 and V.days_old("2025-10-31") == 257
    assert V.mask("37IHKXV5167L1ZS") == "37**********1ZS"
    assert V.mask_udyam("UDYAM-MH-00-9516696") == "UDYAM-MH-00-*****96"
    assert V.mask("SYN-ID-346190", 7, 2) == "SYN-ID-****90"


# ---------------------------------------------------------------------------
# the 12 specimens, expected outcomes per planted problem
# ---------------------------------------------------------------------------
EXPECTED = {
    "K01": ("failed", {"gstin_status": "fail", "udyam_format": "fail"}),
    "K02": ("needs_review", {"gstin_format": "review", "quality_gst_certificate": "review", "gstin_status": "pass", "signatory_authority": "pass"}),
    "K03": ("verified", {}),
    "K04": ("needs_review", {"gstin_format": "review", "quality_gst_certificate": "review", "gstin_registry": "pass"}),
    "K05": ("verified", {"udyam_format": "not_applicable", "signatory_authority": "pass"}),
    "K06": ("failed", {"gstin_format": "fail"}),
    "K07": ("failed", {"name_consistency": "fail", "pan_consistency": "fail"}),
    "K08": ("needs_review", {"gstin_format": "review", "gstin_status": "pass"}),
    "K09": ("verified", {}),
    "K10": ("needs_review", {"signatory_authority": "review"}),
    "K11": ("failed", {"address_proof_recent": "fail"}),
    "K12": ("verified", {}),
}


@pytest.mark.parametrize("applicant", sorted(GOLDEN))
def test_golden_specimen_outcome(applicant):
    result = C.run_checks(GOLDEN[applicant], "gstin")
    overall, expected_checks = EXPECTED[applicant]
    by_code = {c["code"]: c["status"] for c in result["checks"]}
    assert result["overall"] == overall, (applicant, result["summary"], by_code)
    for code, status in expected_checks.items():
        assert by_code.get(code) == status, (applicant, code, by_code.get(code), [c["reason"] for c in result["checks"] if c["code"] == code])
    # identifiers never appear unmasked in reasons
    text = json.dumps(result)
    for doc in GOLDEN[applicant].values():
        for key in ("gstin", "udyam_number", "id_number", "consumer_number"):
            if doc.get(key):
                assert doc[key] not in text, (applicant, key)


def test_udyam_only_path_skips_gst_checks_and_requires_udyam():
    docs = {k: v for k, v in GOLDEN["K03"].items() if k != "gst_certificate"}
    result = C.run_checks(docs, "udyam_only")
    by_code = {c["code"]: c["status"] for c in result["checks"]}
    assert "gstin_format" not in by_code and "gstin_status" not in by_code
    # without a GST record the signatory cannot be matched to an owner: a partner confirms (review, not a dead end)
    assert result["overall"] == "needs_review" and by_code["signatory_authority"] == "review"
    assert by_code["udyam_registry"] == "pass" and by_code["address_consistency"] == "pass"
    missing = C.run_checks({k: v for k, v in docs.items() if k != "udyam_certificate"}, "udyam_only")
    assert missing["overall"] == "failed" and missing["checks"][0]["code"] == "documents_present"


def test_alternative_documents_path_lands_in_review_not_dead_end():
    docs = {k: v for k, v in GOLDEN["K12"].items() if k in ("signatory_id", "address_proof")}
    result = C.run_checks(docs, "alternative_documents")
    assert result["overall"] == "needs_review"
    assert any(c["code"] == "signatory_authority" and c["status"] == "review" for c in result["checks"])


def test_expired_id_and_future_bill_fail():
    docs = json.loads(json.dumps(GOLDEN["K12"]))
    docs["signatory_id"]["valid_till"] = "2026-01-01"
    docs["address_proof"]["bill_date"] = "2026-09-01"
    by_code = {c["code"]: c["status"] for c in C.run_checks(docs, "gstin")["checks"]}
    assert by_code["signatory_id_valid"] == "fail" and by_code["address_proof_recent"] == "fail"


def test_address_mismatch_is_caught():
    docs = json.loads(json.dumps(GOLDEN["K12"]))
    docs["address_proof"]["supply_address"] = "Flat 9, MG Road, Hyderabad, Telangana - 500001"
    by_code = {c["code"]: c["status"] for c in C.run_checks(docs, "gstin")["checks"]}
    assert by_code["address_consistency"] == "fail"


# ---------------------------------------------------------------------------
# consent, case lifecycle, masking, retention
# ---------------------------------------------------------------------------
def test_consent_requires_verification_purpose():
    with pytest.raises(ValueError):
        S.record_consent("s1", {"verification": False, "marketing": True})
    c = S.record_consent("s1", {"verification": True, "marketing": False, "bogus": True})
    assert c["purposes"] == {"verification": True, "marketing": False} and S.has_verification_consent("s1")
    assert not S.has_verification_consent("s2")


def test_case_lifecycle_with_specimen_fallback_and_masking():
    case = S.create_case("s1", "gstin")
    for doc_type in ("gst_certificate", "signatory_id"):
        case = S.add_document(case, doc_type, specimens.specimen_path("K12", doc_type).read_bytes())
    assert case["status"] == "in_progress"
    case = S.add_document(case, "address_proof", specimens.specimen_path("K12", "address_proof").read_bytes())
    assert case["status"] == "verified"
    view = S.masked_view(S.get_case(case["id"]))
    assert view["documents"]["gst_certificate"]["gstin"] == "37**********1ZU"
    assert "_meta" not in view["documents"]["gst_certificate"]
    with pytest.raises(RuntimeError):
        S.add_document(case, "udyam_certificate", b"not a specimen image")


def test_retention_purge_drops_fields_but_keeps_decision():
    case = S.create_case("s1", "gstin")
    S.add_extracted(case, "gst_certificate", GOLDEN["K12"]["gst_certificate"])
    with db.connect() as conn:
        conn.execute("UPDATE kyc_cases SET retention_until = '2000-01-01' WHERE id = ?", (case["id"],))
    assert S.purge_expired() == 1
    loaded = S.get_case(case["id"])
    assert loaded["documents"] == {} and loaded["checks"]


def test_api_consent_upload_and_order_link():
    from app.main import app
    with TestClient(app) as c:
        s = c.post("/api/advisor/sessions", json={"seed_profile": {"business_type": "Electronics retail", "city": "Visakhapatnam", "employee_count": 5, "has_gstin": True}}).json()
        sid = s["session_id"]
        order = c.post("/api/orders", json={"session_id": sid, "lines": [{"product_id": "P01", "quantity": 1}],
                                            "customer": {"business_name": "Star Electronics"}, "payment": {"method": "upi", "reference": "x@upi"}}).json()
        # no consent yet -> refused
        assert c.post("/api/kyc/cases", json={"session_id": sid, "order_id": order["id"]}).status_code == 403
        assert c.get("/api/kyc/consent/purposes").json()[0]["key"] == "verification"
        assert c.post("/api/kyc/consent", json={"session_id": sid, "purposes": {"verification": True}}).status_code == 200
        case = c.post("/api/kyc/cases", json={"session_id": sid, "order_id": order["id"]}).json()
        assert case["path"] == "gstin" and case["required_documents"] == ["gst_certificate", "signatory_id", "address_proof"]
        for doc_type in ("gst_certificate", "signatory_id", "address_proof"):
            r = c.post(f"/api/kyc/cases/{case['id']}/documents/specimen", json={"applicant": "K12", "doc_type": doc_type})
            assert r.status_code == 200, r.text
        done = r.json()
        assert done["status"] == "verified" and done["documents"]["gst_certificate"]["gstin"].startswith("37**")
        assert c.get(f"/api/orders/{order['id']}").json()["current_status"] == "kyc_verified"
        # a failing applicant does not advance the order
        bad = c.post("/api/kyc/cases", json={"session_id": sid}).json()
        for doc_type in ("gst_certificate", "signatory_id", "address_proof"):
            c.post(f"/api/kyc/cases/{bad['id']}/documents/specimen", json={"applicant": "K11", "doc_type": doc_type})
        assert c.get(f"/api/kyc/cases/{bad['id']}").json()["status"] == "failed"
