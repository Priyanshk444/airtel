"""
Data models for the catalogue rule engine.

Everything the engine consumes (BusinessProfile) and produces (Recommendation) is a
pydantic model, so it serialises cleanly to JSON for the API and the advisor.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Segment(str, Enum):
    MICRO = "micro"   # Micro retail & services: kirana, salon, pharmacy, bakery...
    PROF = "prof"     # Professional offices: clinic, CA firm, coaching centre...
    MULTI = "multi"   # Small multi-site businesses: restaurant chain, 3-10 store retailer...
    MFG = "mfg"       # Small manufacturers: auto-parts unit, textile unit...


SEGMENT_LABELS = {
    Segment.MICRO: "Micro retail & services",
    Segment.PROF: "Professional offices",
    Segment.MULTI: "Small multi-site businesses",
    Segment.MFG: "Small manufacturers",
}


class GstinStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"   # has a GSTIN but we have not looked it up yet


class Need(str, Enum):
    """Plain-language needs a business can express. Each maps to an ordered list of products."""
    INTERNET = "internet"                       # reliable internet at the site(s)
    FAST_INTERNET = "fast_internet"             # 1 Gbps class fibre
    DEDICATED_INTERNET = "dedicated_internet"   # leased line with SLA
    DEDICATED_INTERNET_100 = "dedicated_internet_100"
    MOBILE_LINES = "mobile_lines"
    BACKUP_INTERNET = "backup_internet"
    MULTI_SITE_MANAGEMENT = "multi_site_management"
    STATIC_IP = "static_ip"
    CLOUD_TELEPHONY = "cloud_telephony"
    TOLL_FREE = "toll_free"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CLOUD_BACKUP = "cloud_backup"
    WEBSITE = "website"
    POS_BILLING = "pos_billing"
    ENDPOINT_SECURITY = "endpoint_security"
    FIREWALL = "firewall"
    GUEST_WIFI = "guest_wifi"
    CCTV = "cctv"
    MACHINE_MONITORING = "machine_monitoring"
    FLEET_TRACKING = "fleet_tracking"


class BusinessProfile(BaseModel):
    """Structured profile of the business. Everything is optional except what the engine
    can sensibly default; unknown values are treated conservatively."""
    business_type: Optional[str] = None
    segment: Optional[Segment] = None
    employee_count: int = Field(default=1, ge=1)
    num_sites: int = Field(default=1, ge=1)
    city: Optional[str] = None
    city_tier: int = Field(default=2, ge=1, le=2)   # default to tier 2 = the stricter case
    has_gstin: bool = False
    gstin_status: GstinStatus = GstinStatus.UNKNOWN
    has_udyam: bool = False
    current_internet: Optional[str] = None
    current_tools: list[str] = Field(default_factory=list)
    monthly_budget_inr: Optional[int] = Field(default=None, ge=0)
    fibre_feasible: Optional[bool] = None            # None = unknown, assume yes

    needs: list[Need] = Field(default_factory=list)            # what the customer asked for
    excluded_needs: list[Need] = Field(default_factory=list)   # what they said they do not want
    requested_products: list[str] = Field(default_factory=list)  # explicit product IDs
    excluded_products: list[str] = Field(default_factory=list)

    # quantities, when known
    num_mobile_lines: Optional[int] = Field(default=None, ge=0)
    num_users: Optional[int] = Field(default=None, ge=0)      # email seats
    num_devices: Optional[int] = Field(default=None, ge=0)    # PCs / phones to protect
    num_cameras: Optional[int] = Field(default=None, ge=0)
    num_counters: Optional[int] = Field(default=None, ge=0)   # POS counters
    num_vehicles: Optional[int] = Field(default=None, ge=0)
    num_machines: Optional[int] = Field(default=None, ge=0)
    num_channels: Optional[int] = Field(default=None, ge=0)   # telephony channels

    @property
    def gstin_usable(self) -> bool:
        """A GSTIN only unlocks GSTIN-required products if it is not cancelled or suspended.
        Unknown status is accepted provisionally; KYC confirms it later."""
        return self.has_gstin and self.gstin_status in (GstinStatus.ACTIVE, GstinStatus.UNKNOWN)


class Product(BaseModel):
    product_id: str
    category: str
    product_name: str
    description: str
    unit: str
    price_min_inr_per_month: int
    price_max_inr_per_month: int
    one_time_setup_inr: int
    min_contract_months: int
    available_city_tiers: list[int]
    min_employees: int
    min_sites: int
    requires_gstin: bool
    requires_one_of: list[str]
    typical_install_days: int
    target_segments: list[Segment]


class ReasonCode(str, Enum):
    # inclusion
    NEED_MATCH = "need_match"
    SEGMENT_DEFAULT = "segment_default"
    REQUESTED = "requested"
    DEPENDENCY_ADDED = "dependency_added"
    ALTERNATIVE_FOR = "alternative_for"
    # exclusion
    TIER_UNAVAILABLE = "tier_unavailable"
    MIN_EMPLOYEES = "min_employees"
    MIN_SITES = "min_sites"
    GSTIN_REQUIRED = "gstin_required"
    GSTIN_NOT_ACTIVE = "gstin_not_active"
    DEPENDENCY_MISSING = "dependency_missing"
    FIBRE_NOT_FEASIBLE = "fibre_not_feasible"
    CUSTOMER_EXCLUDED = "customer_excluded"
    BUDGET_TRIM = "budget_trim"
    NOT_IN_CATALOGUE = "not_in_catalogue"
    CONFLICT = "conflict"
    NOT_NEEDED = "not_needed"


class Reason(BaseModel):
    code: ReasonCode
    message: str                     # plain English, product names not codes
    related_product_id: Optional[str] = None
    related_need: Optional[Need] = None


class BundleItem(BaseModel):
    product_id: str
    product_name: str
    category: str
    unit: str
    quantity: int
    unit_price_inr: int
    monthly_inr: int
    setup_inr: int
    min_contract_months: int
    install_days: int
    is_core: bool                    # core items cannot be toggled off in the quote
    serves_need: Optional[Need] = None
    reasons: list[Reason]


class Exclusion(BaseModel):
    product_id: str
    product_name: str
    reasons: list[Reason]
    alternative_product_id: Optional[str] = None
    alternative_product_name: Optional[str] = None


class AddOn(BaseModel):
    """An eligible product that is not in the bundle but the customer could add."""
    product_id: str
    product_name: str
    category: str
    unit: str
    description: str
    default_quantity: int
    unit_price_inr: int
    monthly_inr: int
    setup_inr: int
    min_contract_months: int
    install_days: int
    serves_need: Optional[Need] = None
    why: str


class BudgetStatus(str, Enum):
    NO_BUDGET = "no_budget_given"
    WITHIN = "within_budget"
    TRIMMED = "trimmed_to_fit"
    OVER_MINIMUM = "core_bundle_exceeds_budget"


class Pricing(BaseModel):
    monthly_total_inr: int
    setup_total_inr: int
    contract_months: int             # longest minimum contract in the bundle
    expected_install_days: int       # longest install in the bundle
    first_bill_inr: int              # monthly + setup
    budget_status: BudgetStatus
    budget_gap_inr: int = 0          # positive when over budget


class Recommendation(BaseModel):
    segment: Segment
    segment_label: str
    segment_inferred: bool
    items: list[BundleItem]
    excluded: list[Exclusion]
    add_ons: list[AddOn]
    pricing: Pricing
    warnings: list[str]
    kyc_path: str                    # "gstin", "udyam_only" or "alternative_documents"
