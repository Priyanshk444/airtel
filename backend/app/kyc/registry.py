"""Mock GSTIN and Udyam lookup APIs backed by the CSV registries in data/."""
from __future__ import annotations

import csv
from functools import lru_cache

from ..engine.catalogue import data_dir


@lru_cache(maxsize=1)
def _gstin_registry() -> dict[str, dict]:
    with (data_dir() / "mock_gstin_registry.csv").open(newline="", encoding="utf-8") as f:
        return {r["gstin"]: r for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _udyam_registry() -> dict[str, dict]:
    with (data_dir() / "mock_udyam_registry.csv").open(newline="", encoding="utf-8") as f:
        return {r["udyam_number"]: r for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def _lead_contacts() -> dict[str, dict]:
    """Known contact per GSTIN from the CRM (smb_leads.csv) - used only to corroborate the signatory."""
    with (data_dir() / "smb_leads.csv").open(newline="", encoding="utf-8") as f:
        return {r["gstin"]: {"contact_name": r["contact_name"], "contact_role": r["contact_role"], "business_name": r["business_name"]}
                for r in csv.DictReader(f) if r["gstin"]}


def lookup_gstin(gstin: str) -> dict | None:
    """Mock GST portal: returns legal name, trade name, constitution, address, state, registration date, status."""
    r = _gstin_registry().get((gstin or "").strip().upper())
    return dict(r) if r else None


def lookup_udyam(udyam_number: str) -> dict | None:
    """Mock Udyam portal: returns enterprise name, type, activity, state, city, registration date."""
    r = _udyam_registry().get((udyam_number or "").strip().upper())
    return dict(r) if r else None


def find_udyam_by_name(enterprise_name: str, city: str | None = None) -> list[dict]:
    """Helps when the certificate has no number: find candidate registrations by name (and city)."""
    name = (enterprise_name or "").strip().lower()
    out = [dict(r) for r in _udyam_registry().values() if r["enterprise_name"].lower() == name]
    if city:   # same name in another city is a different business, never suggest it
        out = [r for r in out if r["city"].lower() == city.strip().lower()]
    return out


def known_contact(gstin: str) -> dict | None:
    return _lead_contacts().get((gstin or "").strip().upper())
