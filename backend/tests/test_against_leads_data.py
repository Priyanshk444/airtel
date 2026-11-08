"""
Replay every activated bundle in smb_leads.csv through the engine.

docs/data_findings.md section 5c found 48 of 368 sold bundles that break a catalogue rule
(Biz Fibre 1G in tier-2 cities or to <5 staff, Static IP without fibre, GSTIN products to
non-GSTIN leads). Asking the engine for exactly what each lead bought must never reproduce
those violations, and must produce a valid bundle for all 368.
"""
import csv
from pathlib import Path

import pytest

from app.engine import BusinessProfile, GstinStatus, Segment, load_catalogue, recommend
from app.engine.catalogue import data_dir

CAT = load_catalogue()
SEGMENT_MAP = {
    "Micro retail & services": Segment.MICRO, "Professional offices": Segment.PROF,
    "Small multi-site businesses": Segment.MULTI, "Small manufacturers": Segment.MFG,
}


def load_activated():
    with (data_dir() / "smb_leads.csv").open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["outcome"] == "Activated"]


def load_registry_status():
    with (data_dir() / "mock_gstin_registry.csv").open(newline="", encoding="utf-8") as f:
        return {r["gstin"]: r["status"] for r in csv.DictReader(f)}


def parse_bundle(s):
    return {p.split("x")[0]: int(p.split("x")[1]) for p in s.split(";")}


def violations(row, bundle):
    v = []
    tier, emp, sites, gst = int(row["city_tier"]), int(row["employee_count"]), int(row["num_sites"]), row["has_gstin"] == "Y"
    for pid in bundle:
        c = CAT[pid]
        if tier not in c.available_city_tiers: v.append((pid, "tier"))
        if emp < c.min_employees: v.append((pid, "min_emp"))
        if sites < c.min_sites: v.append((pid, "min_sites"))
        if c.requires_gstin and not gst: v.append((pid, "gstin"))
        if c.requires_one_of and not any(d in bundle for d in c.requires_one_of): v.append((pid, "dep"))
    return v


ACTIVATED = load_activated()
REGISTRY = load_registry_status()
VIOLATING = [r for r in ACTIVATED if violations(r, parse_bundle(r["bundle_products"]))]


def profile_from_row(row):
    status = REGISTRY.get(row["gstin"], "")
    return BusinessProfile(
        business_type=row["business_type"], segment=SEGMENT_MAP[row["segment"]], city=row["city"],
        city_tier=int(row["city_tier"]), employee_count=int(row["employee_count"]), num_sites=int(row["num_sites"]),
        has_gstin=row["has_gstin"] == "Y", has_udyam=row["has_udyam"] == "Y",
        gstin_status=GstinStatus(status.lower()) if status else GstinStatus.UNKNOWN,
        requested_products=list(parse_bundle(row["bundle_products"])),
    )


def test_data_contains_the_48_known_violating_sales():
    assert len(ACTIVATED) == 368
    assert len(VIOLATING) == 48


@pytest.mark.parametrize("row", VIOLATING, ids=lambda r: r["lead_id"])
def test_engine_refuses_each_violating_sale(row):
    bundle = parse_bundle(row["bundle_products"])
    rec = recommend(profile_from_row(row))
    chosen = {i.product_id for i in rec.items}
    p = profile_from_row(row)
    effective = {**row, "has_gstin": "Y" if p.gstin_usable else "N"}
    # whatever the engine sold must be legal...
    assert not violations(effective, chosen), f"{row['lead_id']}: engine bundle still breaks a rule"
    # ...and every product it refused must be explained, not dropped silently
    for pid, rule in violations(effective, bundle):
        if pid not in chosen:
            assert pid in {e.product_id for e in rec.excluded}, f"{row['lead_id']}: {pid} refused silently"


def test_all_368_replayed_bundles_are_valid_and_registry_status_is_respected():
    bad_gstin_leads = 0
    for row in ACTIVATED:
        p = profile_from_row(row)
        rec = recommend(p)
        chosen = {i.product_id for i in rec.items}
        assert rec.items, row["lead_id"]
        assert not violations({**row, "has_gstin": "Y" if p.gstin_usable else "N"}, chosen), row["lead_id"]
        if p.has_gstin and not p.gstin_usable:
            bad_gstin_leads += 1
            assert not any(CAT[pid].requires_gstin for pid in chosen), row["lead_id"]
            assert rec.kyc_path != "gstin"
    # the 22 activated customers with cancelled/suspended GSTIN found in Phase 0
    assert bad_gstin_leads == 22


def test_replayed_prices_match_what_customers_actually_paid_when_bundle_is_legal():
    """For legal bundles, requesting exactly the bought products at the bought quantities must
    reproduce the catalogue minimum price, setup and contract that the data shows."""
    checked = 0
    for row in ACTIVATED:
        bundle = parse_bundle(row["bundle_products"])
        if violations(row, bundle):
            continue
        p = profile_from_row(row)
        rec = recommend(p.model_copy(update={"excluded_needs": []}))
        chosen = {i.product_id: i for i in rec.items}
        if set(chosen) != set(bundle):
            continue  # engine added segment defaults the customer did not buy; fine
        setup = sum(CAT[pid].one_time_setup_inr * q for pid, q in bundle.items())
        contract = max(CAT[pid].min_contract_months for pid in bundle)
        assert contract == int(float(row["contract_months"]))
        assert setup == int(float(row["one_time_setup_inr"]))
        assert rec.pricing.contract_months == contract
        checked += 1
    assert checked > 0
