"""Per-product eligibility rules (tier, size, GSTIN, customer exclusions, fibre feasibility)."""
from app.engine import (BusinessProfile, GstinStatus, Need, ReasonCode, eligibility_reasons, is_eligible,
                        load_catalogue)

CAT = load_catalogue()


def codes(product_id: str, profile: BusinessProfile) -> set[ReasonCode]:
    return {r.code for r in eligibility_reasons(CAT[product_id], profile)}


def test_catalogue_loads_25_products_with_parsed_rules():
    assert len(CAT) == 25
    p03 = CAT["P03"]
    assert p03.available_city_tiers == [1] and p03.min_employees == 5 and p03.requires_gstin
    assert CAT["P10"].min_sites == 3 and CAT["P10"].requires_one_of == ["P01", "P02", "P03", "P05", "P06"]
    assert CAT["P01"].requires_one_of == [] and not CAT["P01"].requires_gstin
    assert sum(p.requires_gstin for p in CAT.values()) == 10


def test_tier_rule_only_restricts_biz_fibre_1g():
    tier2 = BusinessProfile(city="Indore", city_tier=2, employee_count=20, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    assert codes("P03", tier2) == {ReasonCode.TIER_UNAVAILABLE}
    assert "Indore" in eligibility_reasons(CAT["P03"], tier2)[0].message
    for pid, product in CAT.items():
        if pid != "P03":
            assert ReasonCode.TIER_UNAVAILABLE not in codes(pid, tier2)
    tier1 = tier2.model_copy(update={"city_tier": 1})
    assert is_eligible(CAT["P03"], tier1)


def test_min_employees_rule():
    small = BusinessProfile(city_tier=1, employee_count=4, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    assert ReasonCode.MIN_EMPLOYEES in codes("P03", small)   # needs 5
    assert ReasonCode.MIN_EMPLOYEES in codes("P05", small)   # needs 10
    assert ReasonCode.MIN_EMPLOYEES in codes("P06", small)   # needs 25
    assert ReasonCode.MIN_EMPLOYEES not in codes("P12", small)  # needs 3
    assert is_eligible(CAT["P05"], small.model_copy(update={"employee_count": 10}))


def test_min_sites_rule_for_sdwan():
    two_sites = BusinessProfile(city_tier=1, employee_count=30, num_sites=2, has_gstin=True, gstin_status=GstinStatus.ACTIVE)
    assert codes("P10", two_sites) == {ReasonCode.MIN_SITES}
    assert is_eligible(CAT["P10"], two_sites.model_copy(update={"num_sites": 3}))


def test_gstin_required_without_gstin():
    p = BusinessProfile(city_tier=1, employee_count=50, num_sites=5, has_gstin=False, has_udyam=True)
    gstin_products = {pid for pid, pr in CAT.items() if pr.requires_gstin}
    for pid in gstin_products:
        assert codes(pid, p) == {ReasonCode.GSTIN_REQUIRED}, pid
    for pid in set(CAT) - gstin_products:
        assert is_eligible(CAT[pid], p), pid


def test_cancelled_or_suspended_gstin_blocks_gstin_products():
    for status in (GstinStatus.CANCELLED, GstinStatus.SUSPENDED):
        p = BusinessProfile(city_tier=1, employee_count=50, has_gstin=True, gstin_status=status)
        assert codes("P15", p) == {ReasonCode.GSTIN_NOT_ACTIVE}
        assert status.value in eligibility_reasons(CAT["P15"], p)[0].message
        assert is_eligible(CAT["P01"], p)  # non-GSTIN products still fine


def test_unknown_gstin_status_is_accepted_provisionally():
    p = BusinessProfile(city_tier=1, employee_count=50, has_gstin=True, gstin_status=GstinStatus.UNKNOWN)
    assert is_eligible(CAT["P15"], p)


def test_customer_exclusions():
    p = BusinessProfile(city_tier=1, excluded_products=["P23"], excluded_needs=[Need.POS_BILLING])
    assert codes("P23", p) == {ReasonCode.CUSTOMER_EXCLUDED}
    assert codes("P19", p) == {ReasonCode.CUSTOMER_EXCLUDED}


def test_fibre_not_feasible_blocks_fibre_only():
    p = BusinessProfile(city_tier=1, employee_count=10, has_gstin=True, gstin_status=GstinStatus.ACTIVE, fibre_feasible=False)
    for pid in ("P01", "P02", "P03"):
        assert ReasonCode.FIBRE_NOT_FEASIBLE in codes(pid, p)
    assert is_eligible(CAT["P04"], p)   # AirFiber is the point
    assert is_eligible(CAT["P05"], p)   # leased line is a separate build


def test_multiple_reasons_are_all_reported():
    p = BusinessProfile(city_tier=2, employee_count=3, has_gstin=False)
    assert codes("P03", p) == {ReasonCode.TIER_UNAVAILABLE, ReasonCode.MIN_EMPLOYEES, ReasonCode.GSTIN_REQUIRED}


def test_messages_use_product_names_not_codes():
    p = BusinessProfile(city_tier=2, employee_count=3, has_gstin=False)
    for r in eligibility_reasons(CAT["P03"], p):
        assert "Biz Fibre 1G" in r.message and "P03" not in r.message
