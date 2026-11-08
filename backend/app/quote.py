"""
Quote repricing: the customer toggles add-ons and quantities; the server rebuilds every line
from the catalogue and the session profile, so prices and eligibility can never be tampered with
from the browser.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .advisor import tools as T
from .engine import BundleItem, Pricing, Reason, ReasonCode, eligibility_reasons, load_catalogue, reprice


class QuoteLine(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=500)


class QuoteRequest(BaseModel):
    session_id: Optional[str] = None
    profile: Optional[dict[str, Any]] = None   # used when there is no advisor session (partner mode)
    lines: list[QuoteLine]


class QuoteIssue(BaseModel):
    product_id: str
    product_name: str
    message: str
    severity: str   # "blocking" (line removed) | "info"


class QuoteResponse(BaseModel):
    items: list[BundleItem]
    pricing: Pricing
    issues: list[QuoteIssue]
    kyc_path: str


def build_quote(profile_dict: dict[str, Any], lines: list[QuoteLine]) -> QuoteResponse:
    """Validate the chosen lines against the profile and price them deterministically."""
    catalogue = load_catalogue()
    profile = T.to_business_profile(profile_dict)
    issues: list[QuoteIssue] = []

    # 1. drop unknown and ineligible products (with the engine's reasons)
    chosen: dict[str, int] = {}
    for line in lines:
        pid = line.product_id.upper()
        product = catalogue.get(pid)
        if not product:
            issues.append(QuoteIssue(product_id=pid, product_name=pid, message="Not a catalogue product.", severity="blocking"))
            continue
        reasons = eligibility_reasons(product, profile)
        if reasons:
            issues.append(QuoteIssue(product_id=pid, product_name=product.product_name,
                                     message=" ".join(r.message for r in reasons), severity="blocking"))
            continue
        chosen[pid] = chosen.get(pid, 0) + line.quantity

    # 2. dependencies: a dependent product needs its base link in the same quote
    changed = True
    while changed:
        changed = False
        for pid in list(chosen):
            product = catalogue[pid]
            if product.requires_one_of and not any(d in chosen for d in product.requires_one_of):
                names = " or ".join(catalogue[d].product_name for d in product.requires_one_of)
                issues.append(QuoteIssue(product_id=pid, product_name=product.product_name, severity="blocking",
                                         message=f"{product.product_name} needs {names} in the same order. Add an internet line first."))
                del chosen[pid]
                changed = True

    # 3. rebuild items from the catalogue
    items: list[BundleItem] = []
    for pid, qty in chosen.items():
        p = catalogue[pid]
        items.append(BundleItem(
            product_id=pid, product_name=p.product_name, category=p.category, unit=p.unit, quantity=qty,
            unit_price_inr=p.price_min_inr_per_month, monthly_inr=p.price_min_inr_per_month * qty,
            setup_inr=p.one_time_setup_inr * qty, min_contract_months=p.min_contract_months,
            install_days=p.typical_install_days, is_core=False, serves_need=None,
            reasons=[Reason(code=ReasonCode.REQUESTED, message="Selected on the quote screen.")]))
    items.sort(key=lambda i: i.product_id)

    kyc_path = "gstin" if profile.gstin_usable else ("udyam_only" if profile.has_udyam else "alternative_documents")
    return QuoteResponse(items=items, pricing=reprice(items), issues=issues, kyc_path=kyc_path)
