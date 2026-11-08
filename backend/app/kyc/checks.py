"""
KYC validation checks. Input: extracted fields per document. Output: a list of CheckResult with
pass / fail / review and a plain-language reason, plus an overall decision.

Document keys: gst_certificate, udyam_certificate, signatory_id, address_proof.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import registry as reg
from . import validators as V

PASS, FAIL, REVIEW, SKIP = "pass", "fail", "review", "not_applicable"
BILL_MAX_AGE_DAYS = 90
NAME_PASS, NAME_REVIEW = 90, 75
ADDR_PASS, ADDR_REVIEW = 90, 75
LOW_CONFIDENCE = 0.75


@dataclass
class CheckResult:
    code: str
    title: str
    status: str
    reason: str
    documents: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(doc: dict | None, key: str) -> str | None:
    if not doc:
        return None
    v = doc.get(key)
    if isinstance(v, str):
        v = v.strip()
    return v or None


def run_checks(documents: dict[str, dict], kyc_path: str) -> dict[str, Any]:
    """kyc_path: 'gstin' | 'udyam_only' | 'alternative_documents' (decided by the engine / profile)."""
    gst = documents.get("gst_certificate")
    ud = documents.get("udyam_certificate")
    sid = documents.get("signatory_id")
    bill = documents.get("address_proof")
    results: list[CheckResult] = []
    ctx: dict[str, Any] = {}   # values shared between checks (e.g. the repaired GSTIN, registry records)

    results += check_documents_present(documents, kyc_path)
    results += check_document_quality(documents)
    if gst or kyc_path == "gstin":
        results += check_gstin(gst, ctx)
        results += check_gst_registry(gst, ctx)
        results += check_pan_consistency(gst, ud, bill, ctx)
    results += check_udyam(ud, gst, ctx, kyc_path)
    results += check_names(gst, ud, sid, bill, ctx)
    results += check_signatory(gst, sid, ctx)
    results += check_address(gst, ud, bill, ctx)
    results += check_address_proof_recency(bill)

    statuses = [r.status for r in results]
    if FAIL in statuses:
        overall = "failed"
    elif REVIEW in statuses:
        overall = "needs_review"
    else:
        overall = "verified"
    return {
        "overall": overall,
        "summary": summarise(results, overall),
        "checks": [r.to_dict() for r in results],
        "counts": {s: statuses.count(s) for s in (PASS, FAIL, REVIEW, SKIP)},
        "resolved": {
            "gstin": V.mask(ctx.get("gstin")), "gstin_status": ctx.get("gstin_status"),
            "udyam_number": V.mask_udyam(ctx.get("udyam_number")), "trade_name": ctx.get("trade_name"),
        },
    }


def summarise(results: list[CheckResult], overall: str) -> str:
    problems = [r for r in results if r.status in (FAIL, REVIEW)]
    if overall == "verified":
        return "All checks passed. Your business is verified and the order can move to installation."
    fixes = "; ".join(r.reason for r in problems[:4])
    if overall == "failed":
        return f"We could not verify the business yet: {fixes}"
    return f"A few things need a quick look by our team: {fixes}"


# ---------------------------------------------------------------------------
# presence and quality
# ---------------------------------------------------------------------------
REQUIRED_BY_PATH = {
    "gstin": ["gst_certificate", "signatory_id", "address_proof"],
    "udyam_only": ["udyam_certificate", "signatory_id", "address_proof"],
    "alternative_documents": ["signatory_id", "address_proof"],
}
DOC_LABELS = {"gst_certificate": "GST certificate", "udyam_certificate": "Udyam certificate",
              "signatory_id": "authorised signatory ID", "address_proof": "address proof (utility bill)"}


def check_documents_present(documents: dict[str, dict], kyc_path: str) -> list[CheckResult]:
    required = REQUIRED_BY_PATH.get(kyc_path, REQUIRED_BY_PATH["gstin"])
    missing = [DOC_LABELS[d] for d in required if d not in documents]
    optional_missing = [DOC_LABELS[d] for d in DOC_LABELS if d not in documents and d not in required]
    if missing:
        return [CheckResult("documents_present", "Required documents uploaded", FAIL,
                            "Missing: " + ", ".join(missing) + ".", details={"missing": missing})]
    reason = f"All documents required for the {kyc_path.replace('_', ' ')} path are present."
    if optional_missing:
        reason += " Not provided (optional for this path): " + ", ".join(optional_missing) + "."
    return [CheckResult("documents_present", "Required documents uploaded", PASS, reason)]


def check_document_quality(documents: dict[str, dict]) -> list[CheckResult]:
    out = []
    for key, doc in documents.items():
        legibility = (doc.get("legibility") or "clear").lower()
        conf = doc.get("confidence")
        try:
            conf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf = None
        poor = legibility not in ("clear", "good") or (conf is not None and conf < LOW_CONFIDENCE)
        if poor:
            out.append(CheckResult(f"quality_{key}", f"Image quality: {DOC_LABELS[key]}", REVIEW,
                                   f"The {DOC_LABELS[key]} is {legibility}" + (f" (reader confidence {conf:.0%})" if conf is not None else "")
                                   + ". Values read from it will be double-checked by our team; a clearer photo speeds this up.",
                                   [key], {"legibility": legibility, "confidence": conf}))
    return out


# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------
def check_gstin(gst: dict | None, ctx: dict) -> list[CheckResult]:
    raw = _f(gst, "gstin")
    if not raw:
        return [CheckResult("gstin_format", "GSTIN format and checksum", FAIL, "No GSTIN could be read from the GST certificate.", ["gst_certificate"])]
    raw = raw.upper().replace(" ", "")
    if V.gstin_checksum_ok(raw):
        ctx["gstin"] = raw
        return [CheckResult("gstin_format", "GSTIN format and checksum", PASS,
                            f"GSTIN {V.mask(raw)} has the correct 15-character structure and checksum.", ["gst_certificate"])]
    repaired, subs = V.repair_gstin(raw)
    if repaired:
        ctx["gstin"] = repaired
        ctx["gstin_repaired"] = True
        return [CheckResult("gstin_format", "GSTIN format and checksum", REVIEW,
                            f"GSTIN as printed fails the format check ({'; '.join(subs)}). It looks like a letter/digit mix-up; "
                            f"{V.mask(repaired)} passes the checksum and was used for the registry lookup. Please confirm with the customer.",
                            ["gst_certificate"], {"as_read": V.mask(raw), "candidate": V.mask(repaired), "substitutions": subs})]
    return [CheckResult("gstin_format", "GSTIN format and checksum", FAIL,
                        f"GSTIN {V.mask(raw)} is not a valid GSTIN (structure or checksum is wrong). Ask for a clear photo of the certificate.",
                        ["gst_certificate"])]


def check_gst_registry(gst: dict | None, ctx: dict) -> list[CheckResult]:
    gstin = ctx.get("gstin")
    if not gstin:
        return [CheckResult("gstin_registry", "GSTIN found in GST registry", SKIP, "Skipped because no valid GSTIN was available.")]
    record = reg.lookup_gstin(gstin)
    out: list[CheckResult] = []
    if not record:
        out.append(CheckResult("gstin_registry", "GSTIN found in GST registry", FAIL,
                               f"GSTIN {V.mask(gstin)} is not in the GST registry.", ["gst_certificate"]))
        return out
    ctx["gst_record"] = record
    ctx["gstin_status"] = record["status"]
    out.append(CheckResult("gstin_registry", "GSTIN found in GST registry", PASS,
                           f"GSTIN {V.mask(gstin)} is registered to {record['legal_name']} in {record['state']}.", ["gst_certificate"]))

    # status
    status = record["status"]
    if status.lower() == "active":
        out.append(CheckResult("gstin_status", "GSTIN status", PASS, "GST registration is active.", ["gst_certificate"]))
    else:
        out.append(CheckResult("gstin_status", "GSTIN status", FAIL,
                               f"GST registration is {status.lower()} in the registry. GST-only products cannot be sold; "
                               f"the customer can continue with Udyam or other documents for the rest of the bundle.", ["gst_certificate"]))

    # certificate vs registry
    legal_sim = V.name_similarity(_f(gst, "legal_name"), record["legal_name"])
    trade_sim = V.name_similarity(_f(gst, "trade_name"), record["trade_name"])
    addr_sim = V.address_similarity(_f(gst, "address"), record["principal_place_of_business"])
    if legal_sim >= NAME_PASS and trade_sim >= NAME_PASS and addr_sim >= ADDR_PASS:
        out.append(CheckResult("gst_certificate_matches_registry", "Certificate details match the registry", PASS,
                               "Legal name, trade name and address on the certificate match the registry record.", ["gst_certificate"],
                               {"legal_name": legal_sim, "trade_name": trade_sim, "address": addr_sim}))
    else:
        weak = [n for n, s, t in (("legal name", legal_sim, NAME_REVIEW), ("trade name", trade_sim, NAME_REVIEW), ("address", addr_sim, ADDR_REVIEW)) if s < t]
        status_ = FAIL if weak else REVIEW
        out.append(CheckResult("gst_certificate_matches_registry", "Certificate details match the registry", status_,
                               ("The certificate differs from the registry on: " + ", ".join(weak) + ".") if weak else
                               "Small differences between the certificate and the registry record.", ["gst_certificate"],
                               {"legal_name": legal_sim, "trade_name": trade_sim, "address": addr_sim}))

    # registration date
    cert_date = V.parse_date(_f(gst, "date_of_liability"))
    reg_date = V.parse_date(record["registration_date"])
    if cert_date and reg_date:
        out.append(CheckResult("gst_registration_date", "Registration date matches the registry", PASS if cert_date == reg_date else REVIEW,
                               "Date of liability on the certificate matches the registry." if cert_date == reg_date else
                               f"Certificate shows {cert_date} but the registry shows {reg_date}.", ["gst_certificate"]))

    # state code vs address
    state_from_code = V.gstin_state(gstin)
    addr = V.norm_text(_f(gst, "address"))
    if state_from_code and addr:
        ok = V.norm_text(state_from_code) in addr
        out.append(CheckResult("gstin_state_code", "GSTIN state code matches the address", PASS if ok else FAIL,
                               f"State code {gstin[:2]} = {state_from_code}, which {'matches' if ok else 'does not match'} the address on the certificate.",
                               ["gst_certificate"]))
    return out


def check_pan_consistency(gst: dict | None, ud: dict | None, bill: dict | None, ctx: dict) -> list[CheckResult]:
    gstin = ctx.get("gstin")
    if not gstin:
        return [CheckResult("pan_consistency", "PAN inside the GSTIN matches the other documents", SKIP, "Skipped: no valid GSTIN.")]
    pan = V.pan_from_gstin(gstin)
    problems = []
    if pan[3] != "X":   # README: synthetic PANs always carry X as entity type; real-world would be a lookup table
        problems.append(f"4th PAN character '{pan[3]}' is not a valid entity type")
    initial = pan[4]
    names = [n for n in (_f(gst, "trade_name"), _f(ud, "enterprise_name"), _f(bill, "billed_to")) if n]
    _, legal_trade = V.proprietor_from_legal_name(_f(gst, "legal_name"))
    if legal_trade:
        names.append(legal_trade)
    mismatched = [n for n in names if not V.norm_text(n).startswith(initial.lower())]
    if mismatched:
        problems.append(f"PAN name letter '{initial}' does not match: " + ", ".join(sorted(set(mismatched))))
    record = ctx.get("gst_record")
    if record and V.pan_from_gstin(record["gstin"]) != pan:
        problems.append("PAN in the registry record differs")
    if problems:
        return [CheckResult("pan_consistency", "PAN inside the GSTIN matches the other documents", FAIL if len(problems) > 1 or mismatched else REVIEW,
                            "; ".join(problems) + ".", ["gst_certificate", "udyam_certificate", "address_proof"], {"pan": V.mask(pan, 0, 2)})]
    return [CheckResult("pan_consistency", "PAN inside the GSTIN matches the other documents", PASS,
                        f"PAN {V.mask(pan, 0, 2)} embedded in the GSTIN is consistent with the business name on every document.",
                        ["gst_certificate", "udyam_certificate", "address_proof"])]


# ---------------------------------------------------------------------------
# Udyam
# ---------------------------------------------------------------------------
def check_udyam(ud: dict | None, gst: dict | None, ctx: dict, kyc_path: str) -> list[CheckResult]:
    if not ud:
        if kyc_path == "udyam_only":
            return [CheckResult("udyam_format", "Udyam registration number", FAIL, "Udyam certificate is required when there is no GSTIN.", ["udyam_certificate"])]
        return [CheckResult("udyam_format", "Udyam registration number", SKIP, "No Udyam certificate provided; not required on the GSTIN path.")]
    out: list[CheckResult] = []
    number = _f(ud, "udyam_number")
    name = _f(ud, "enterprise_name")
    if not number:
        candidates = reg.find_udyam_by_name(name or "", _f(ud, "city"))
        hint = (f" The registry has a registration for {name} in {_f(ud, 'city')} ({V.mask_udyam(candidates[0]['udyam_number'])}); "
                f"ask the customer to confirm it.") if candidates else ""
        out.append(CheckResult("udyam_format", "Udyam registration number", FAIL,
                               "The Udyam certificate has no registration number printed on it." + hint, ["udyam_certificate"]))
        return out
    parts = V.udyam_parts(number)
    if not parts:
        out.append(CheckResult("udyam_format", "Udyam registration number", FAIL,
                               f"{V.mask_udyam(number)} is not in the UDYAM-XX-00-0000000 format.", ["udyam_certificate"]))
        return out
    ctx["udyam_number"] = number.upper()
    state_on_cert = _f(ud, "state")
    state_ok = not state_on_cert or not parts["state"] or V.norm_text(parts["state"]) == V.norm_text(state_on_cert)
    out.append(CheckResult("udyam_format", "Udyam registration number", PASS if state_ok else FAIL,
                           f"{V.mask_udyam(number)} is well-formed" + (f" and its state code {parts['state_abbr']} matches {state_on_cert}." if state_ok else
                                                                      f" but its state code {parts['state_abbr']} ({parts['state']}) does not match the state on the certificate ({state_on_cert})."),
                           ["udyam_certificate"]))
    record = reg.lookup_udyam(number)
    if not record:
        out.append(CheckResult("udyam_registry", "Udyam number found in registry", FAIL, f"{V.mask_udyam(number)} is not in the Udyam registry.", ["udyam_certificate"]))
        return out
    ctx["udyam_record"] = record
    sim = V.name_similarity(name, record["enterprise_name"])
    city_ok = V.norm_text(record["city"]) == V.norm_text(_f(ud, "city")) if _f(ud, "city") else True
    if sim >= NAME_PASS and city_ok:
        out.append(CheckResult("udyam_registry", "Udyam number found in registry", PASS,
                               f"Registered to {record['enterprise_name']} ({record['enterprise_type']}, {record['major_activity']}) in {record['city']}.", ["udyam_certificate"]))
    else:
        out.append(CheckResult("udyam_registry", "Udyam number found in registry", FAIL if sim < NAME_REVIEW else REVIEW,
                               f"The registry lists this number under {record['enterprise_name']} in {record['city']}, which does not match the certificate.",
                               ["udyam_certificate"], {"name_similarity": sim}))
    # Udyam <-> GSTIN consistency
    gstin = ctx.get("gstin")
    if gstin and gst:
        issues = []
        if V.name_similarity(name, _f(gst, "trade_name")) < NAME_REVIEW:
            issues.append("enterprise name differs from the GST trade name")
        gst_state = V.gstin_state(gstin)
        if gst_state and parts["state"] and V.norm_text(gst_state) != V.norm_text(parts["state"]):
            issues.append(f"Udyam state ({parts['state']}) differs from GSTIN state ({gst_state})")
        if _f(ud, "city") and V.norm_text(_f(ud, "city")) not in V.norm_text(_f(gst, "address")):
            issues.append("Udyam city is not in the GST address")
        out.append(CheckResult("udyam_gstin_consistency", "Udyam and GSTIN describe the same business", PASS if not issues else FAIL,
                               "Udyam and GST records agree on name, state and city." if not issues else "; ".join(issues) + ".",
                               ["udyam_certificate", "gst_certificate"]))
    return out


# ---------------------------------------------------------------------------
# names, signatory, address, recency
# ---------------------------------------------------------------------------
def check_names(gst, ud, sid, bill, ctx) -> list[CheckResult]:
    names = {
        "GST trade name": _f(gst, "trade_name"), "Udyam enterprise name": _f(ud, "enterprise_name"),
        "business on signatory ID": _f(sid, "business_name"), "name on bill": _f(bill, "billed_to"),
    }
    names = {k: v for k, v in names.items() if v}
    issues = []
    if gst:
        proprietor, legal_trade = V.proprietor_from_legal_name(_f(gst, "legal_name"))
        ctx["proprietor"] = proprietor
        if legal_trade and V.name_similarity(legal_trade, _f(gst, "trade_name")) < NAME_PASS:
            issues.append(f"the legal name says the business is '{legal_trade}' but the trade name is '{_f(gst, 'trade_name')}'")
        elif not legal_trade and _f(gst, "legal_name") and V.name_similarity(_f(gst, "legal_name"), _f(gst, "trade_name")) < NAME_REVIEW:
            issues.append("legal name and trade name on the GST certificate differ")
    anchor_key = next(iter(names), None)
    if anchor_key:
        anchor = names[anchor_key]
        ctx["trade_name"] = anchor
        for k, v in names.items():
            s = V.name_similarity(anchor, v, ignore_suffixes=False)
            if s < NAME_REVIEW:
                issues.append(f"{k} '{v}' does not match {anchor_key} '{anchor}'")
            elif s < NAME_PASS:
                issues.append(f"{k} '{v}' is only a near match to '{anchor}'")
    if not names:
        return [CheckResult("name_consistency", "Business name is consistent across documents", SKIP, "No business names to compare.")]
    if not issues:
        return [CheckResult("name_consistency", "Business name is consistent across documents", PASS,
                            f"'{names[anchor_key]}' appears consistently on all {len(names)} documents.", list(names.keys()))]
    hard = any("does not match" in i or "legal name says" in i for i in issues)
    return [CheckResult("name_consistency", "Business name is consistent across documents", FAIL if hard else REVIEW,
                        "; ".join(issues).capitalize() + ".", list(names.keys()))]


def check_signatory(gst, sid, ctx) -> list[CheckResult]:
    if not sid:
        return [CheckResult("signatory_id_valid", "Authorised signatory ID", FAIL, "No signatory ID provided.", ["signatory_id"])]
    out = []
    valid_till = V.parse_date(_f(sid, "valid_till"))
    if valid_till is None:
        out.append(CheckResult("signatory_id_valid", "Signatory ID is valid", REVIEW, "Could not read the ID's validity date.", ["signatory_id"]))
    elif valid_till < V.today():
        out.append(CheckResult("signatory_id_valid", "Signatory ID is valid", FAIL, f"The signatory ID expired on {valid_till}.", ["signatory_id"]))
    else:
        out.append(CheckResult("signatory_id_valid", "Signatory ID is valid", PASS, f"ID {V.mask(_f(sid, 'id_number'), 7, 2)} is valid until {valid_till}.", ["signatory_id"]))

    person = _f(sid, "name")
    designation = (_f(sid, "designation") or "").lower()
    constitution = (_f(gst, "constitution") or (ctx.get("gst_record") or {}).get("constitution") or "").lower()
    proprietor = ctx.get("proprietor")
    if proprietor:
        sim = V.person_similarity(person, proprietor)
        if sim >= NAME_PASS:
            out.append(CheckResult("signatory_authority", "Signatory is authorised for this business", PASS,
                                   f"{person} is the proprietor named on the GST certificate.", ["signatory_id", "gst_certificate"]))
        else:
            contact = reg.known_contact(ctx.get("gstin", ""))
            known = contact and V.person_similarity(person, contact["contact_name"]) >= NAME_PASS
            out.append(CheckResult("signatory_authority", "Signatory is authorised for this business", REVIEW,
                                   f"{person} ({designation or 'no designation'}) is not the proprietor ({proprietor}) named on the GST certificate"
                                   + (", but matches the contact on record." if known else ". A letter of authority from the proprietor is needed."),
                                   ["signatory_id", "gst_certificate"]))
    elif constitution:
        contact = reg.known_contact(ctx.get("gstin", ""))
        known = bool(contact and V.person_similarity(person, contact["contact_name"]) >= NAME_PASS)
        # which designations can sign for which entity type ("owner" is not a legal role in an LLP or company)
        if "partnership" in constitution:
            plausible = any(w in designation for w in ("partner", "authorised", "authorized"))
        elif "company" in constitution or "ltd" in constitution:
            plausible = any(w in designation for w in ("director", "authorised", "authorized", "secretary"))
        else:
            plausible = any(w in designation for w in ("owner", "proprietor", "partner", "director", "authorised", "authorized"))
        status = PASS if known else (PASS if plausible else REVIEW)
        out.append(CheckResult("signatory_authority", "Signatory is authorised for this business", status,
                               f"{person} signs as '{designation or 'unspecified'}' for a {constitution}" + (" and matches the contact on record." if known else
                               "; the designation is valid for this entity type." if plausible else
                               f", but '{designation}' is not a signing role for this entity type and the person is not the contact on record. "
                               "A partner/board resolution naming the signatory is needed."),
                               ["signatory_id", "gst_certificate"]))
    else:
        out.append(CheckResult("signatory_authority", "Signatory is authorised for this business", REVIEW,
                               f"{person} ({designation or 'no designation'}) cannot be matched to a registered owner without a GST record; a partner will confirm.",
                               ["signatory_id"]))
    return out


def check_address(gst, ud, bill, ctx) -> list[CheckResult]:
    gst_addr, bill_addr = _f(gst, "address"), _f(bill, "supply_address")
    if not bill_addr:
        return [CheckResult("address_consistency", "Address proof matches the registered address", FAIL if bill else SKIP,
                            "Could not read a supply address from the address proof." if bill else "No address proof provided.", ["address_proof"])]
    if not gst_addr:
        # Udyam-only path: compare city/state only
        city, state = _f(ud, "city"), _f(ud, "state")
        text = V.norm_text(bill_addr)
        ok = (not city or V.norm_text(city) in text) and (not state or V.norm_text(state) in text)
        return [CheckResult("address_consistency", "Address proof matches the registered address", PASS if ok else FAIL,
                            f"Bill address {'is in' if ok else 'is not in'} {city}, {state} as per the Udyam certificate.", ["address_proof", "udyam_certificate"])]
    sim = V.address_similarity(gst_addr, bill_addr)
    pin_gst, pin_bill = V.pincode(gst_addr), V.pincode(bill_addr)
    pin_ok = not (pin_gst and pin_bill) or pin_gst == pin_bill
    if sim >= ADDR_PASS and pin_ok:
        status, reason = PASS, "The utility bill is for the same address as the GST registration."
    elif sim >= ADDR_REVIEW and pin_ok:
        status, reason = REVIEW, "The bill address is close to the registered address but not identical."
    else:
        status, reason = FAIL, "The bill is for a different address than the GST registration" + ("" if pin_ok else " (different PIN code)") + "."
    return [CheckResult("address_consistency", "Address proof matches the registered address", status, reason,
                        ["address_proof", "gst_certificate"], {"similarity": sim, "pin_match": pin_ok})]


def check_address_proof_recency(bill) -> list[CheckResult]:
    if not bill:
        return [CheckResult("address_proof_recent", "Address proof is recent", SKIP, "No address proof provided.")]
    age = V.days_old(_f(bill, "bill_date"))
    if age is None:
        return [CheckResult("address_proof_recent", "Address proof is recent", REVIEW, "Could not read the bill date.", ["address_proof"])]
    if age < 0:
        return [CheckResult("address_proof_recent", "Address proof is recent", FAIL, f"The bill is dated in the future ({_f(bill, 'bill_date')}).", ["address_proof"])]
    if age > BILL_MAX_AGE_DAYS:
        return [CheckResult("address_proof_recent", "Address proof is recent", FAIL,
                            f"The bill is {age} days old; address proof must be no older than {BILL_MAX_AGE_DAYS} days. Please upload a recent bill.",
                            ["address_proof"], {"days_old": age})]
    return [CheckResult("address_proof_recent", "Address proof is recent", PASS, f"The bill is {age} days old (limit {BILL_MAX_AGE_DAYS}).", ["address_proof"], {"days_old": age})]
