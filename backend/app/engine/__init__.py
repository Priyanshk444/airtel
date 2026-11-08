"""Deterministic catalogue rule engine. No LLM involvement anywhere in this package."""
from .catalogue import get_product, load_catalogue
from .models import (AddOn, BudgetStatus, BundleItem, BusinessProfile, Exclusion, GstinStatus, Need,
                     Pricing, Product, Reason, ReasonCode, Recommendation, Segment, SEGMENT_LABELS)
from .recommend import recommend, reprice
from .rules import eligibility_reasons, infer_segment, is_eligible

__all__ = [
    "AddOn", "BudgetStatus", "BundleItem", "BusinessProfile", "Exclusion", "GstinStatus", "Need",
    "Pricing", "Product", "Reason", "ReasonCode", "Recommendation", "Segment", "SEGMENT_LABELS",
    "recommend", "reprice", "eligibility_reasons", "infer_segment", "is_eligible",
    "get_product", "load_catalogue",
]
