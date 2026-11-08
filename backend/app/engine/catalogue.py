"""Load product_catalogue.csv into Product models."""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

from .models import Product, Segment

# The data directory can be overridden (e.g. in Docker the pack is mounted at /data).
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def data_dir() -> Path:
    return Path(os.environ.get("UDYAM_DATA_DIR", DEFAULT_DATA_DIR))


def _split(value: str, sep: str) -> list[str]:
    value = (value or "").strip()
    return [v for v in value.split(sep) if v] if value else []


def _row_to_product(row: dict) -> Product:
    return Product(
        product_id=row["product_id"],
        category=row["category"],
        product_name=row["product_name"],
        description=row["description"],
        unit=row["unit"],
        price_min_inr_per_month=int(row["price_min_inr_per_month"]),
        price_max_inr_per_month=int(row["price_max_inr_per_month"]),
        one_time_setup_inr=int(row["one_time_setup_inr"]),
        min_contract_months=int(row["min_contract_months"]),
        available_city_tiers=[int(t) for t in _split(row["available_city_tiers"], ";")],
        min_employees=int(row["min_employees"]),
        min_sites=int(row["min_sites"]),
        requires_gstin=row["requires_gstin"].strip().upper() == "Y",
        requires_one_of=_split(row["requires_one_of"], "|"),
        typical_install_days=int(row["typical_install_days"]),
        target_segments=[Segment(s) for s in _split(row["target_segments"], ";")],
    )


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Product]:
    path = data_dir() / "product_catalogue.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return {row["product_id"]: _row_to_product(row) for row in csv.DictReader(f)}


def get_product(product_id: str) -> Product | None:
    return load_catalogue().get(product_id.upper())
