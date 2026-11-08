"""
The rules: product eligibility, need -> product preference lists, and per-segment defaults.

Eligibility rules come straight from product_catalogue.csv (tier, min employees, min sites,
GSTIN, requires_one_of). The need maps and segment templates encode what each segment
actually bought in smb_leads.csv (see docs/data_findings.md section 5 and 8).
"""
from __future__ import annotations

from .models import BusinessProfile, Need, Product, Reason, ReasonCode, Segment

# ---------------------------------------------------------------------------
# Segment inference from business type keywords (used only when segment not given)
# ---------------------------------------------------------------------------
MICRO_TYPES = ["kirana", "general store", "salon", "pharmacy", "medical store", "chemist", "bakery",
               "sweet", "stationery", "boutique", "mobile repair", "hardware", "optician", "shop",
               "store", "parlour", "tailor", "cafe", "tea stall", "dhaba", "restaurant", "grocery"]
PROF_TYPES = ["clinic", "dental", "physio", "diagnostic", "lab", "ca firm", "chartered", "accountant",
              "coaching", "tuition", "classes", "law", "advocate", "legal", "architect", "design studio",
              "real estate", "realty", "insurance", "travel", "agency", "consult", "office", "doctor"]
MFG_TYPES = ["unit", "manufactur", "factory", "workshop", "press", "moulding", "packaging", "textile",
             "auto-parts", "auto parts", "food processing", "mill", "fabrication", "plant"]
MULTI_HINTS = ["chain", "stores", "branches", "outlets", "hotel group", "franchise"]


def infer_segment(profile: BusinessProfile) -> Segment:
    text = (profile.business_type or "").lower()
    if profile.num_sites >= 3 or any(k in text for k in MULTI_HINTS):
        return Segment.MULTI
    if any(k in text for k in MFG_TYPES):
        return Segment.MFG
    if any(k in text for k in PROF_TYPES):
        return Segment.PROF
    if any(k in text for k in MICRO_TYPES):
        return Segment.MICRO
    # no keyword: size decides
    if profile.num_sites == 2:
        return Segment.MULTI
    return Segment.PROF if profile.employee_count > 10 else Segment.MICRO


# ---------------------------------------------------------------------------
# Need -> ordered product preferences (best fit first). The engine takes the first
# eligible product; the rest are the "nearest alternatives".
# ---------------------------------------------------------------------------
INTERNET_PREFERENCE: dict[Segment, list[str]] = {
    Segment.MICRO: ["P01", "P04"],
    Segment.PROF: ["P02", "P01", "P04"],
    Segment.MULTI: ["P02", "P01", "P04"],
    Segment.MFG: ["P05", "P03", "P02", "P01", "P04"],
}

NEED_PRODUCTS: dict[Need, list[str]] = {
    Need.INTERNET: [],  # resolved per segment via INTERNET_PREFERENCE
    Need.FAST_INTERNET: ["P03", "P02", "P01"],
    Need.DEDICATED_INTERNET: ["P05", "P03", "P02", "P01"],
    Need.DEDICATED_INTERNET_100: ["P06", "P05", "P03", "P02"],
    Need.MOBILE_LINES: [],  # resolved per segment
    Need.BACKUP_INTERNET: ["P09"],
    Need.MULTI_SITE_MANAGEMENT: ["P10"],
    Need.STATIC_IP: ["P11"],
    Need.CLOUD_TELEPHONY: ["P12"],
    Need.TOLL_FREE: ["P13"],
    Need.SMS: ["P14"],
    Need.WHATSAPP: ["P15"],
    Need.EMAIL: ["P16"],
    Need.CLOUD_BACKUP: ["P17"],
    Need.WEBSITE: ["P18"],
    Need.POS_BILLING: ["P19"],
    Need.ENDPOINT_SECURITY: ["P20"],
    Need.FIREWALL: ["P21"],
    Need.GUEST_WIFI: ["P22"],
    Need.CCTV: ["P23"],
    Need.MACHINE_MONITORING: ["P24"],
    Need.FLEET_TRACKING: ["P25"],
}

CONNECTIVITY_NEEDS = {Need.INTERNET, Need.FAST_INTERNET, Need.DEDICATED_INTERNET, Need.DEDICATED_INTERNET_100}

# Reverse map: which need does a product serve (for explaining and for alternatives)
PRODUCT_NEED: dict[str, Need] = {
    "P01": Need.INTERNET, "P02": Need.INTERNET, "P03": Need.FAST_INTERNET, "P04": Need.INTERNET,
    "P05": Need.DEDICATED_INTERNET, "P06": Need.DEDICATED_INTERNET_100,
    "P07": Need.MOBILE_LINES, "P08": Need.MOBILE_LINES,
    "P09": Need.BACKUP_INTERNET, "P10": Need.MULTI_SITE_MANAGEMENT, "P11": Need.STATIC_IP,
    "P12": Need.CLOUD_TELEPHONY, "P13": Need.TOLL_FREE, "P14": Need.SMS, "P15": Need.WHATSAPP,
    "P16": Need.EMAIL, "P17": Need.CLOUD_BACKUP, "P18": Need.WEBSITE, "P19": Need.POS_BILLING,
    "P20": Need.ENDPOINT_SECURITY, "P21": Need.FIREWALL, "P22": Need.GUEST_WIFI, "P23": Need.CCTV,
    "P24": Need.MACHINE_MONITORING, "P25": Need.FLEET_TRACKING,
}

NEED_LABELS: dict[Need, str] = {
    Need.INTERNET: "reliable internet at your site",
    Need.FAST_INTERNET: "very fast (1 Gbps) internet",
    Need.DEDICATED_INTERNET: "dedicated internet with an uptime guarantee",
    Need.DEDICATED_INTERNET_100: "dedicated 100 Mbps internet with an uptime guarantee",
    Need.MOBILE_LINES: "mobile lines for your team",
    Need.BACKUP_INTERNET: "a backup link so you stay online if the main line fails",
    Need.MULTI_SITE_MANAGEMENT: "one place to manage internet across all your sites",
    Need.STATIC_IP: "a fixed public IP for cameras, servers or remote access",
    Need.CLOUD_TELEPHONY: "business phone lines with IVR and call recording",
    Need.TOLL_FREE: "a toll-free 1800 number",
    Need.SMS: "bulk SMS for alerts and promotions",
    Need.WHATSAPP: "a verified WhatsApp Business channel",
    Need.EMAIL: "business email on your own domain",
    Need.CLOUD_BACKUP: "automatic backup of your computers and phones",
    Need.WEBSITE: "a simple website with your own domain",
    Need.POS_BILLING: "GST-ready billing and UPI/card acceptance",
    Need.ENDPOINT_SECURITY: "antivirus and ransomware protection",
    Need.FIREWALL: "a managed firewall at your site",
    Need.GUEST_WIFI: "secure Wi-Fi with a separate network for customers",
    Need.CCTV: "cloud CCTV you can view on your phone",
    Need.MACHINE_MONITORING: "sensors to monitor machine uptime and energy",
    Need.FLEET_TRACKING: "GPS tracking for your vehicles",
}

# ---------------------------------------------------------------------------
# Segment templates: core needs (always in the bundle) and recommended needs
# (pre-included but toggleable). Based on what each segment actually bought.
# ---------------------------------------------------------------------------
SEGMENT_CORE: dict[Segment, list[Need]] = {
    Segment.MICRO: [Need.INTERNET, Need.MOBILE_LINES],
    Segment.PROF: [Need.INTERNET, Need.MOBILE_LINES, Need.EMAIL],
    Segment.MULTI: [Need.INTERNET, Need.BACKUP_INTERNET, Need.MOBILE_LINES],
    Segment.MFG: [Need.DEDICATED_INTERNET, Need.MOBILE_LINES, Need.EMAIL],
}
SEGMENT_RECOMMENDED: dict[Segment, list[Need]] = {
    Segment.MICRO: [Need.POS_BILLING],
    Segment.PROF: [Need.ENDPOINT_SECURITY, Need.CLOUD_BACKUP],
    Segment.MULTI: [Need.MULTI_SITE_MANAGEMENT, Need.POS_BILLING],
    Segment.MFG: [Need.ENDPOINT_SECURITY],
}
# Products shown as optional add-ons for the segment (if eligible and not already included)
SEGMENT_ADDONS: dict[Segment, list[Need]] = {
    Segment.MICRO: [Need.WHATSAPP, Need.GUEST_WIFI, Need.CCTV, Need.WEBSITE, Need.POS_BILLING, Need.SMS, Need.BACKUP_INTERNET],
    Segment.PROF: [Need.BACKUP_INTERNET, Need.CLOUD_TELEPHONY, Need.STATIC_IP, Need.SMS, Need.WHATSAPP,
                   Need.TOLL_FREE, Need.GUEST_WIFI, Need.WEBSITE, Need.ENDPOINT_SECURITY, Need.CLOUD_BACKUP],
    Segment.MULTI: [Need.CCTV, Need.TOLL_FREE, Need.WHATSAPP, Need.GUEST_WIFI, Need.FLEET_TRACKING,
                    Need.CLOUD_TELEPHONY, Need.SMS, Need.MULTI_SITE_MANAGEMENT, Need.POS_BILLING, Need.EMAIL],
    Segment.MFG: [Need.FIREWALL, Need.MACHINE_MONITORING, Need.CCTV, Need.FLEET_TRACKING, Need.CLOUD_BACKUP,
                  Need.BACKUP_INTERNET, Need.STATIC_IP, Need.ENDPOINT_SECURITY],
}
# POS only makes sense where customers pay at a counter
POS_TYPES = ["kirana", "store", "shop", "pharmacy", "chemist", "bakery", "sweet", "boutique", "retail",
             "restaurant", "cafe", "hotel", "salon", "optician", "hardware", "stationery", "grocery", "mobile"]


def pos_relevant(profile: BusinessProfile, segment: Segment) -> bool:
    text = (profile.business_type or "").lower()
    if any(k in text for k in POS_TYPES):
        return True
    return segment == Segment.MICRO and not text  # unknown micro business: assume a counter


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------
def eligibility_reasons(product: Product, profile: BusinessProfile) -> list[Reason]:
    """Return the reasons a product is NOT eligible for this profile. Empty list = eligible.
    Dependency (requires_one_of) is checked separately at bundle level."""
    reasons: list[Reason] = []
    name = product.product_name
    if profile.city_tier not in product.available_city_tiers:
        reasons.append(Reason(
            code=ReasonCode.TIER_UNAVAILABLE, related_product_id=product.product_id,
            message=f"{name} is only available in tier-{'/'.join(map(str, product.available_city_tiers))} cities"
                    f"{', and ' + profile.city + ' is a tier-' + str(profile.city_tier) + ' city' if profile.city else ', and your city is tier ' + str(profile.city_tier)}."))
    if profile.employee_count < product.min_employees:
        reasons.append(Reason(
            code=ReasonCode.MIN_EMPLOYEES, related_product_id=product.product_id,
            message=f"{name} is offered to businesses with at least {product.min_employees} employees; you have {profile.employee_count}."))
    if profile.num_sites < product.min_sites:
        reasons.append(Reason(
            code=ReasonCode.MIN_SITES, related_product_id=product.product_id,
            message=f"{name} is for businesses with at least {product.min_sites} sites; you have {profile.num_sites}."))
    if product.requires_gstin:
        if not profile.has_gstin:
            reasons.append(Reason(
                code=ReasonCode.GSTIN_REQUIRED, related_product_id=product.product_id,
                message=f"{name} can only be sold to a GST-registered business, and you do not have a GSTIN yet."))
        elif not profile.gstin_usable:
            reasons.append(Reason(
                code=ReasonCode.GSTIN_NOT_ACTIVE, related_product_id=product.product_id,
                message=f"{name} needs an active GSTIN; yours is {profile.gstin_status.value} in the GST registry."))
    if product.product_id in profile.excluded_products:
        reasons.append(Reason(
            code=ReasonCode.CUSTOMER_EXCLUDED, related_product_id=product.product_id,
            message=f"You asked us not to include {name}."))
    need = PRODUCT_NEED.get(product.product_id)
    if need and need in profile.excluded_needs:
        reasons.append(Reason(
            code=ReasonCode.CUSTOMER_EXCLUDED, related_product_id=product.product_id, related_need=need,
            message=f"You said you do not need {NEED_LABELS[need]}."))
    # Wired products at a site where fibre is not feasible
    if profile.fibre_feasible is False and product.product_id in ("P01", "P02", "P03"):
        reasons.append(Reason(
            code=ReasonCode.FIBRE_NOT_FEASIBLE, related_product_id=product.product_id,
            message=f"{name} needs a fibre line and fibre is not feasible at your site."))
    return reasons


def is_eligible(product: Product, profile: BusinessProfile) -> bool:
    return not eligibility_reasons(product, profile)
