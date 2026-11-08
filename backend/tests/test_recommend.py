"""Bundle building, dependency resolution, pricing, budget and edge cases."""
import itertools
import random

import pytest

from app.engine import (BudgetStatus, BusinessProfile, GstinStatus, Need, ReasonCode, Segment, infer_segment,
                        load_catalogue, recommend, reprice)

CAT = load_catalogue()
BASE_LINKS = {"P01", "P02", "P03", "P04", "P05", "P06"}


def ids(rec) -> set[str]:
    return {i.product_id for i in rec.items}


def excluded_ids(rec) -> set[str]:
    return {e.product_id for e in rec.excluded}


def item(rec, pid):
    return next(i for i in rec.items if i.product_id == pid)


def excl(rec, pid):
    return next(e for e in rec.excluded if e.product_id == pid)


def assert_bundle_valid(rec, profile):
    """Invariant every recommendation must satisfy."""
    bundle = ids(rec)
    for i in rec.items:
        p = CAT[i.product_id]
        assert profile.city_tier in p.available_city_tiers, i.product_id
        assert profile.employee_count >= p.min_employees, i.product_id
        assert profile.num_sites >= p.min_sites, i.product_id
        assert not p.requires_gstin or profile.gstin_usable, i.product_id
        assert not p.requires_one_of or any(d in bundle for d in p.requires_one_of), i.product_id
        assert i.product_id not in profile.excluded_products
        assert i.quantity >= 1 and i.monthly_inr == i.unit_price_inr * i.quantity
        assert i.unit_price_inr == p.price_min_inr_per_month
        assert i.setup_inr == p.one_time_setup_inr * i.quantity
        assert i.reasons, "every item must carry a reason"
        for r in i.reasons:
            assert "P0" not in r.message and "P1" not in r.message and "P2" not in r.message
    # pricing follows the catalogue rule used by every activated bundle in the data
    assert rec.pricing.monthly_total_inr == sum(i.monthly_inr for i in rec.items)
    assert rec.pricing.setup_total_inr == sum(i.setup_inr for i in rec.items)
    assert rec.pricing.contract_months == max((i.min_contract_months for i in rec.items), default=0)
    assert rec.pricing.expected_install_days == max((i.install_days for i in rec.items), default=0)
    assert rec.pricing.first_bill_inr == rec.pricing.monthly_total_inr + rec.pricing.setup_total_inr
    # at most one internet line unless the customer asked for two kinds
    assert len(bundle & BASE_LINKS) <= 1
    # add-ons are eligible, not already in the bundle, and their dependencies are satisfied
    for a in rec.add_ons:
        p = CAT[a.product_id]
        assert a.product_id not in bundle
        assert profile.city_tier in p.available_city_tiers and profile.employee_count >= p.min_employees
        assert not p.requires_gstin or profile.gstin_usable
        assert not p.requires_one_of or any(d in bundle for d in p.requires_one_of)
    for e in rec.excluded:
        assert e.reasons and e.product_id not in bundle


# ---------------------------------------------------------------------------
# segment inference
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("btype,emp,sites,expected", [
    ("Kirana store", 2, 1, Segment.MICRO), ("Salon", 3, 1, Segment.MICRO), ("Pharmacy", 4, 1, Segment.MICRO),
    ("Dental clinic", 8, 1, Segment.PROF), ("CA firm", 12, 1, Segment.PROF), ("Coaching centre", 6, 1, Segment.PROF),
    ("Restaurant chain", 40, 5, Segment.MULTI), ("Boutique", 10, 3, Segment.MULTI),
    ("Auto-parts unit", 30, 1, Segment.MFG), ("Textile unit", 20, 1, Segment.MFG), ("Printing press", 9, 1, Segment.MFG),
    (None, 2, 1, Segment.MICRO), (None, 15, 1, Segment.PROF), (None, 15, 2, Segment.MULTI),
])
def test_segment_inference(btype, emp, sites, expected):
    assert infer_segment(BusinessProfile(business_type=btype, employee_count=emp, num_sites=sites)) == expected


def test_explicit_segment_wins_over_inference():
    rec = recommend(BusinessProfile(business_type="Kirana store", segment=Segment.PROF, employee_count=2))
    assert rec.segment == Segment.PROF and not rec.segment_inferred


# ---------------------------------------------------------------------------
# default bundles per segment
# ---------------------------------------------------------------------------
def test_micro_default_bundle_is_small_and_needs_no_gstin():
    p = BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2, has_udyam=True)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert {"P01", "P07", "P19"} == ids(rec)
    assert item(rec, "P01").is_core and item(rec, "P07").is_core and not item(rec, "P19").is_core
    assert rec.pricing.monthly_total_inr == 999 + 299 + 599
    assert rec.pricing.contract_months == 12 and rec.pricing.expected_install_days == 5
    assert rec.kyc_path == "udyam_only"


def test_prof_default_bundle():
    p = BusinessProfile(business_type="Dental clinic", city_tier=1, employee_count=8, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert ids(rec) == {"P02", "P07", "P16", "P17", "P20"}
    assert item(rec, "P16").quantity == 8 and item(rec, "P20").quantity == 8
    assert item(rec, "P07").quantity == 3          # min(3, employees) lines
    assert rec.kyc_path == "gstin"


def test_prof_with_10_plus_staff_gets_premium_lines():
    rec = recommend(BusinessProfile(business_type="Law office", city_tier=1, employee_count=15, has_gstin=True))
    assert "P08" in ids(rec) and "P07" not in ids(rec)


def test_multi_site_quantities_scale_per_site():
    p = BusinessProfile(business_type="Pharmacy chain", city_tier=1, employee_count=45, num_sites=5,
                        has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert ids(rec) == {"P02", "P09", "P08", "P10", "P19"}
    for pid in ("P02", "P09", "P10", "P19"):
        assert item(rec, pid).quantity == 5, pid
    assert item(rec, "P08").quantity == 5
    assert rec.pricing.contract_months == 24   # SD-WAN has a 24-month minimum
    assert rec.pricing.expected_install_days == 14
    assert rec.pricing.setup_total_inr == 5 * (1500 + 5000 + 2500)


def test_multi_site_without_gstin_gets_no_sdwan_but_still_a_bundle():
    p = BusinessProfile(business_type="Bakery chain", city_tier=2, employee_count=30, num_sites=4, has_udyam=True)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P10" not in ids(rec) and "P10" in excluded_ids(rec)
    assert excl(rec, "P10").reasons[0].code == ReasonCode.GSTIN_REQUIRED
    assert {"P02", "P09", "P08", "P19"} <= ids(rec)


def test_manufacturer_default_gets_leased_line_when_big_enough():
    p = BusinessProfile(business_type="Auto-parts unit", city_tier=2, employee_count=40, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P05" in ids(rec) and item(rec, "P05").is_core
    assert item(rec, "P16").quantity == 40
    assert rec.pricing.expected_install_days == 21 and rec.pricing.contract_months == 12
    assert "P11" not in ids(rec)  # static IP does not run on a leased line in this catalogue


def test_small_manufacturer_falls_back_to_fibre():
    p = BusinessProfile(business_type="Furniture workshop", city_tier=2, employee_count=6, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P02" in ids(rec)
    assert "P05" in excluded_ids(rec) and excl(rec, "P05").alternative_product_id == "P02"
    assert item(rec, "P02").reasons[0].code == ReasonCode.ALTERNATIVE_FOR


# ---------------------------------------------------------------------------
# requested products, alternatives and conflicts
# ---------------------------------------------------------------------------
def test_tier2_customer_wanting_1g_gets_300m_with_explanation():
    p = BusinessProfile(business_type="CA firm", city="Indore", city_tier=2, employee_count=12, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, requested_products=["P03"])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P03" not in ids(rec) and "P02" in ids(rec)
    e = excl(rec, "P03")
    assert e.reasons[0].code == ReasonCode.TIER_UNAVAILABLE and e.alternative_product_id == "P02"
    assert "Indore" in e.reasons[0].message
    assert item(rec, "P02").reasons[0].code == ReasonCode.ALTERNATIVE_FOR
    assert "Biz Fibre 1G" in item(rec, "P02").reasons[0].message


def test_tier1_customer_wanting_1g_gets_it():
    p = BusinessProfile(business_type="Diagnostic lab", city_tier=1, employee_count=12, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, requested_products=["P03"])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P03" in ids(rec) and item(rec, "P03").reasons[0].code == ReasonCode.REQUESTED
    assert "P02" not in ids(rec)


def test_no_gstin_wanting_whatsapp_api_is_refused_with_reason():
    p = BusinessProfile(business_type="Boutique", city_tier=1, employee_count=3, has_udyam=True, needs=[Need.WHATSAPP])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P15" not in ids(rec)
    assert excl(rec, "P15").reasons[0].code == ReasonCode.GSTIN_REQUIRED
    assert any("GSTIN" in w for w in rec.warnings)
    assert "P15" not in {a.product_id for a in rec.add_ons}


def test_cancelled_gstin_is_treated_as_no_gstin_for_gst_products():
    p = BusinessProfile(business_type="Salon", city_tier=1, employee_count=2, has_gstin=True,
                        gstin_status=GstinStatus.CANCELLED, has_udyam=True, needs=[Need.WHATSAPP, Need.SMS])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert not ({"P15", "P14"} & ids(rec))
    assert excl(rec, "P15").reasons[0].code == ReasonCode.GSTIN_NOT_ACTIVE
    assert rec.kyc_path == "udyam_only"
    assert any("cancelled" in w for w in rec.warnings)


def test_leased_line_for_8_person_unit_falls_back_to_fibre_300():
    p = BusinessProfile(business_type="Textile unit", city_tier=2, employee_count=8, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, requested_products=["P05"])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P05" not in ids(rec) and "P02" in ids(rec)
    e = excl(rec, "P05")
    assert e.reasons[0].code == ReasonCode.MIN_EMPLOYEES and e.alternative_product_id == "P02"
    assert "Internet Leased Line 20" in item(rec, "P02").reasons[0].message


def test_sdwan_for_single_site_refused():
    p = BusinessProfile(business_type="Boutique", city_tier=1, employee_count=12, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, requested_products=["P10"])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P10" not in ids(rec)
    assert excl(rec, "P10").reasons[0].code == ReasonCode.MIN_SITES
    assert any("3 sites" in w for w in rec.warnings)


def test_conflicting_internet_requests_keep_the_most_capable_and_warn():
    p = BusinessProfile(business_type="Packaging unit", city_tier=1, employee_count=30, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, needs=[Need.INTERNET, Need.DEDICATED_INTERNET, Need.FAST_INTERNET])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert ids(rec) & BASE_LINKS == {"P05"}
    assert any("more than one kind of internet" in w for w in rec.warnings)


def test_unknown_product_id_is_ignored_with_warning():
    p = BusinessProfile(business_type="Kirana store", requested_products=["P99", "p01"])
    rec = recommend(p)
    assert "P01" in ids(rec)
    assert any("P99" in w for w in rec.warnings)


def test_change_of_mind_removes_item_and_puts_it_in_addons():
    base = BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2)
    rec1 = recommend(base)
    assert "P19" in ids(rec1)
    rec2 = recommend(base.model_copy(update={"excluded_needs": [Need.POS_BILLING]}))
    assert "P19" not in ids(rec2)
    assert "P19" not in {a.product_id for a in rec2.add_ons}  # customer said no; do not re-offer
    rec3 = recommend(base.model_copy(update={"excluded_products": ["P07"]}))
    assert "P07" not in ids(rec3)


def test_pos_not_pushed_on_non_retail_professional():
    rec = recommend(BusinessProfile(business_type="Law office", city_tier=1, employee_count=6, has_gstin=True))
    assert "P19" not in ids(rec)


# ---------------------------------------------------------------------------
# dependencies
# ---------------------------------------------------------------------------
def test_cctv_alone_pulls_in_an_internet_line():
    p = BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2, segment=Segment.MICRO,
                        excluded_needs=[Need.MOBILE_LINES, Need.POS_BILLING], needs=[Need.CCTV], num_cameras=3)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P23" in ids(rec) and item(rec, "P23").quantity == 3
    assert ids(rec) & BASE_LINKS  # a link was kept/added


def test_dependency_added_when_customer_excluded_generic_internet_but_wants_wifi():
    # excluding the INTERNET need removes P01/P02/P04 as candidates; Wi-Fi then has no base
    p = BusinessProfile(business_type="Salon", city_tier=1, employee_count=2, excluded_needs=[Need.INTERNET], needs=[Need.GUEST_WIFI])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert "P22" not in ids(rec)
    e = excl(rec, "P22")
    assert e.reasons[0].code == ReasonCode.DEPENDENCY_MISSING
    assert "do not need" in e.reasons[0].message


def test_failover_requested_with_airfiber_only_is_dropped_not_double_linked():
    p = BusinessProfile(business_type="Coaching centre", city_tier=2, employee_count=6, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, fibre_feasible=False, needs=[Need.BACKUP_INTERNET, Need.STATIC_IP])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert ids(rec) & BASE_LINKS == {"P04"}
    for pid in ("P09", "P11"):
        assert pid not in ids(rec)
        assert excl(rec, pid).reasons[0].code == ReasonCode.DEPENDENCY_MISSING
        assert "AirFiber" in excl(rec, pid).reasons[0].message


def test_static_ip_requested_on_fibre_is_fine():
    p = BusinessProfile(business_type="Dental clinic", city_tier=1, employee_count=6, has_gstin=True, needs=[Need.STATIC_IP])
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert {"P02", "P11"} <= ids(rec)


def test_wifi_not_offered_as_addon_on_leased_line():
    p = BusinessProfile(business_type="Auto-parts unit", city_tier=2, employee_count=40, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    rec = recommend(p)
    assert "P05" in ids(rec)
    assert "P22" not in {a.product_id for a in rec.add_ons}   # P22 requires P01-P04
    assert "P21" in {a.product_id for a in rec.add_ons}       # firewall works on leased line


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------
def test_budget_trims_optional_items_largest_first():
    p = BusinessProfile(business_type="Dental clinic", city_tier=1, employee_count=10, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, monthly_budget_inr=5000)
    full = recommend(p.model_copy(update={"monthly_budget_inr": None}))
    assert full.pricing.monthly_total_inr > 5000
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert rec.pricing.budget_status == BudgetStatus.TRIMMED
    assert rec.pricing.monthly_total_inr <= 5000
    trimmed = [e for e in rec.excluded if e.reasons[0].code == ReasonCode.BUDGET_TRIM]
    assert trimmed and all(not item(full, e.product_id).is_core for e in trimmed)
    # trimmed items are offered back as add-ons
    assert {e.product_id for e in trimmed} <= {a.product_id for a in rec.add_ons}


def test_budget_too_low_for_core_is_reported_not_silently_cut():
    p = BusinessProfile(business_type="Law office", city_tier=1, employee_count=15, has_gstin=True,
                        gstin_status=GstinStatus.ACTIVE, monthly_budget_inr=2000)
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert rec.pricing.budget_status == BudgetStatus.OVER_MINIMUM
    assert all(i.is_core for i in rec.items)
    assert rec.pricing.budget_gap_inr == rec.pricing.monthly_total_inr - 2000 > 0


def test_budget_within_leaves_bundle_untouched():
    p = BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2, monthly_budget_inr=3000)
    rec = recommend(p)
    assert rec.pricing.budget_status == BudgetStatus.WITHIN and ids(rec) == {"P01", "P07", "P19"}


def test_requested_items_are_core_and_survive_budget_trim():
    p = BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2, needs=[Need.CCTV], monthly_budget_inr=1700)
    rec = recommend(p)
    assert "P23" in ids(rec) and "P19" not in ids(rec)


# ---------------------------------------------------------------------------
# pricing helpers
# ---------------------------------------------------------------------------
def test_reprice_after_toggling_addons():
    rec = recommend(BusinessProfile(business_type="Kirana store", city_tier=2, employee_count=2))
    kept = [i for i in rec.items if i.is_core]
    pricing = reprice(kept)
    assert pricing.monthly_total_inr == 999 + 299 and pricing.setup_total_inr == 0
    assert pricing.contract_months == 12 and pricing.expected_install_days == 5


def test_empty_profile_still_produces_a_valid_starter_bundle():
    p = BusinessProfile()
    rec = recommend(p)
    assert_bundle_valid(rec, p)
    assert rec.segment == Segment.MICRO and {"P01", "P07"} <= ids(rec)
    assert rec.kyc_path == "alternative_documents"


def test_zero_lines_requested_means_no_mobile_item():
    p = BusinessProfile(business_type="Kirana store", num_mobile_lines=0)
    rec = recommend(p)
    assert "P07" not in ids(rec) and "P08" not in ids(rec)


# ---------------------------------------------------------------------------
# invariant sweep over many generated profiles
# ---------------------------------------------------------------------------
def test_invariants_hold_across_generated_profiles():
    rng = random.Random(7)
    types = ["Kirana store", "Salon", "Dental clinic", "CA firm", "Restaurant chain", "Pharmacy chain",
             "Auto-parts unit", "Textile unit", None]
    all_needs = list(Need)
    for _ in range(400):
        needs = rng.sample(all_needs, rng.randint(0, 4))
        requested = rng.sample(list(CAT), rng.randint(0, 2))
        p = BusinessProfile(
            business_type=rng.choice(types), city_tier=rng.choice([1, 2]), employee_count=rng.choice([1, 3, 5, 9, 10, 25, 60]),
            num_sites=rng.choice([1, 1, 2, 3, 6]), has_gstin=rng.random() < 0.7,
            gstin_status=rng.choice(list(GstinStatus)), has_udyam=rng.random() < 0.5,
            fibre_feasible=rng.choice([None, True, False]), monthly_budget_inr=rng.choice([None, None, 1500, 5000, 20000]),
            needs=needs, requested_products=requested, excluded_needs=rng.sample(all_needs, rng.randint(0, 2)),
            num_cameras=rng.choice([None, 0, 4]), num_vehicles=rng.choice([None, 0, 3]), num_machines=rng.choice([None, 0, 5]),
        )
        rec = recommend(p)
        assert_bundle_valid(rec, p)


def test_every_segment_tier_gstin_combination_is_valid():
    for seg, tier, gst in itertools.product(list(Segment), [1, 2], [True, False]):
        p = BusinessProfile(segment=seg, city_tier=tier, employee_count=12, num_sites=3 if seg == Segment.MULTI else 1,
                            has_gstin=gst, gstin_status=GstinStatus.ACTIVE if gst else GstinStatus.UNKNOWN)
        rec = recommend(p)
        assert_bundle_valid(rec, p)
        assert rec.items, (seg, tier, gst)


def test_requested_leased_line_wins_over_more_capable_ask():
    """S05 live run: the model recorded both leased-line needs; the exclusion shown must be for the line the customer named."""
    prof = BusinessProfile(business_type="Textile unit", city_tier=2, employee_count=8, has_gstin=True,
                           needs=[Need.DEDICATED_INTERNET, Need.DEDICATED_INTERNET_100], requested_products=["P05"])
    rec = recommend(prof)
    assert [e.product_id for e in rec.excluded] == ["P05"]
    assert rec.excluded[0].reasons[0].code.value == "min_employees"
    assert any(i.product_id == "P02" for i in rec.items)
