"""
Build and price a recommended bundle for a business profile.

Algorithm
1. Infer the segment if not given.
2. Collect needs: segment core needs + segment recommended needs + customer needs
   + needs implied by explicitly requested products, minus excluded needs.
3. For each need pick the first eligible product in its preference list (quantity sized from
   the profile). Ineligible products become Exclusions with the nearest eligible alternative.
4. Resolve dependencies: a product that requires one of a set of base links either finds one
   in the bundle, gets the cheapest eligible base link added, or is dropped with a reason.
5. Price: list price = catalogue minimum per unit x quantity; setup = sum of one-time fees;
   contract = longest minimum contract; install = longest install. (This is exactly how every
   activated bundle in smb_leads.csv was priced.)
6. Budget: if a monthly budget is given and exceeded, drop optional items (largest first)
   until it fits; if the core alone exceeds the budget, say so.
7. Add-ons: other eligible products that fit the segment, with default quantities.
"""
from __future__ import annotations

from .catalogue import load_catalogue
from .models import (AddOn, BudgetStatus, BundleItem, BusinessProfile, Exclusion, Need, Pricing,
                     Product, Reason, ReasonCode, Recommendation, Segment, SEGMENT_LABELS)
from .rules import (CONNECTIVITY_NEEDS, INTERNET_PREFERENCE, NEED_LABELS, NEED_PRODUCTS, PRODUCT_NEED,
                    SEGMENT_ADDONS, SEGMENT_CORE, SEGMENT_RECOMMENDED, eligibility_reasons, infer_segment,
                    pos_relevant)

BASE_LINKS = ["P01", "P02", "P03", "P04", "P05", "P06"]


# ---------------------------------------------------------------------------
# quantities
# ---------------------------------------------------------------------------
def default_quantity(product: Product, profile: BusinessProfile, segment: Segment) -> int:
    unit = product.unit
    if unit == "per site":
        return profile.num_sites
    if unit == "per line":
        if profile.num_mobile_lines is not None:
            return max(profile.num_mobile_lines, 0)
        return {Segment.MICRO: 1, Segment.PROF: min(3, profile.employee_count),
                Segment.MULTI: profile.num_sites, Segment.MFG: 2}[segment]
    if unit == "per user":
        return profile.num_users if profile.num_users is not None else profile.employee_count
    if unit == "per device":
        if product.product_id == "P24":  # machine sensors
            return profile.num_machines if profile.num_machines is not None else 0
        return profile.num_devices if profile.num_devices is not None else profile.employee_count
    if unit == "per camera":
        return profile.num_cameras if profile.num_cameras is not None else 2 * profile.num_sites
    if unit == "per counter":
        return profile.num_counters if profile.num_counters is not None else profile.num_sites
    if unit == "per vehicle":
        return profile.num_vehicles if profile.num_vehicles is not None else 0
    if unit == "per channel":
        return profile.num_channels if profile.num_channels is not None else 2
    return 1  # per IP, per number, per pack, per account


# ---------------------------------------------------------------------------
# product selection per need
# ---------------------------------------------------------------------------
def preference_list(need: Need, segment: Segment, profile: BusinessProfile) -> list[str]:
    if need == Need.INTERNET:
        prefs = list(INTERNET_PREFERENCE[segment])
        if profile.fibre_feasible is False:
            prefs = ["P04"] + [p for p in prefs if p != "P04"]
        return prefs
    if need == Need.MOBILE_LINES:
        if segment == Segment.MICRO or (segment == Segment.PROF and profile.employee_count < 10):
            return ["P07", "P08"]
        return ["P08", "P07"]
    return list(NEED_PRODUCTS[need])


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def recommend(profile: BusinessProfile) -> Recommendation:
    catalogue = load_catalogue()
    warnings: list[str] = []

    segment_inferred = profile.segment is None
    segment = profile.segment or infer_segment(profile)

    # --- 1. collect needs -------------------------------------------------------------
    core_needs = list(SEGMENT_CORE[segment])
    recommended_needs = [n for n in SEGMENT_RECOMMENDED[segment]
                         if not (n == Need.POS_BILLING and not pos_relevant(profile, segment))]
    customer_needs = list(profile.needs)

    # explicitly requested products imply their need
    requested_ids = [p.upper() for p in profile.requested_products]
    unknown = [p for p in requested_ids if p not in catalogue]
    requested_ids = [p for p in requested_ids if p in catalogue]
    for p in unknown:
        warnings.append(f"'{p}' is not a product in the Accel Business catalogue and was ignored.")
    for pid in requested_ids:
        need = PRODUCT_NEED[pid]
        if need not in customer_needs:
            customer_needs.append(need)

    # A customer asking for a specific internet class replaces the generic internet need
    if any(n in customer_needs for n in CONNECTIVITY_NEEDS - {Need.INTERNET}):
        core_needs = [n for n in core_needs if n not in CONNECTIVITY_NEEDS]
        if Need.INTERNET in customer_needs and len([n for n in customer_needs if n in CONNECTIVITY_NEEDS]) > 1:
            customer_needs.remove(Need.INTERNET)
    # A manufacturer who only says "internet" still gets the dedicated preference list
    if segment == Segment.MFG and Need.INTERNET in customer_needs and Need.DEDICATED_INTERNET in core_needs:
        customer_needs.remove(Need.INTERNET)
        if Need.DEDICATED_INTERNET not in customer_needs:
            customer_needs.append(Need.DEDICATED_INTERNET)
    # Conflicting connectivity asks: keep the most capable one
    conn_asks = [n for n in customer_needs if n in CONNECTIVITY_NEEDS]
    if len(conn_asks) > 1:
        order = [Need.DEDICATED_INTERNET_100, Need.DEDICATED_INTERNET, Need.FAST_INTERNET, Need.INTERNET]
        # the line the customer named by product wins; otherwise the most capable ask
        requested = [PRODUCT_NEED[p] for p in profile.requested_products if PRODUCT_NEED.get(p) in conn_asks]
        keep = requested[0] if requested else min(conn_asks, key=order.index)
        for n in conn_asks:
            if n != keep:
                customer_needs.remove(n)
        warnings.append(f"You asked for more than one kind of internet line; we quoted {NEED_LABELS[keep]} "
                        f"and you can add a backup link if you want a second connection.")

    excluded_needs = set(profile.excluded_needs)
    core_needs = [n for n in core_needs if n not in excluded_needs]
    recommended_needs = [n for n in recommended_needs if n not in excluded_needs and n not in core_needs]
    customer_needs = [n for n in customer_needs if n not in excluded_needs]

    # ordered, de-duplicated need list with its origin
    plan: list[tuple[Need, str]] = []
    seen: set[Need] = set()
    for need in customer_needs:
        if need not in seen:
            plan.append((need, "requested")); seen.add(need)
    for need in core_needs:
        if need not in seen:
            plan.append((need, "core")); seen.add(need)
    for need in recommended_needs:
        if need not in seen:
            plan.append((need, "recommended")); seen.add(need)

    # --- 2. pick products ----------------------------------------------------------------
    items: dict[str, BundleItem] = {}
    excluded: list[Exclusion] = []

    def make_item(product: Product, need: Need | None, is_core: bool, reasons: list[Reason]) -> BundleItem | None:
        qty = default_quantity(product, profile, segment)
        if qty <= 0:
            return None
        return BundleItem(
            product_id=product.product_id, product_name=product.product_name, category=product.category,
            unit=product.unit, quantity=qty, unit_price_inr=product.price_min_inr_per_month,
            monthly_inr=product.price_min_inr_per_month * qty, setup_inr=product.one_time_setup_inr * qty,
            min_contract_months=product.min_contract_months, install_days=product.typical_install_days,
            is_core=is_core, serves_need=need, reasons=reasons)

    for need, origin in plan:
        if need in (Need.FLEET_TRACKING, Need.MACHINE_MONITORING) and origin != "requested":
            continue  # never pre-include per-vehicle / per-machine items unless asked
        prefs = preference_list(need, segment, profile)
        requested_pid = next((p for p in requested_ids if PRODUCT_NEED[p] == need), None)
        if requested_pid:
            prefs = [requested_pid] + [p for p in prefs if p != requested_pid]

        chosen: Product | None = None
        rejected: list[tuple[Product, list[Reason]]] = []
        for pid in prefs:
            reasons = eligibility_reasons(catalogue[pid], profile)
            if reasons:
                rejected.append((catalogue[pid], reasons))
            else:
                chosen = catalogue[pid]
                break

        # The product the customer asked for (or the best fit) was not eligible: explain it
        primary = rejected[0] if rejected else None
        if primary and (origin == "requested" or chosen is None or primary[0].product_id == requested_pid
                        or need in CONNECTIVITY_NEEDS):
            excluded.append(Exclusion(
                product_id=primary[0].product_id, product_name=primary[0].product_name, reasons=primary[1],
                alternative_product_id=chosen.product_id if chosen else None,
                alternative_product_name=chosen.product_name if chosen else None))

        if chosen is None:
            first_reason = primary[1][0].message if primary else ""
            if origin == "requested":
                warnings.append(f"We could not offer {NEED_LABELS[need]}. {first_reason}")
            elif origin == "core":
                warnings.append(f"No eligible option for {NEED_LABELS[need]}. {first_reason}")
            continue
        if chosen.product_id in items:
            items[chosen.product_id].reasons.append(Reason(
                code=ReasonCode.NEED_MATCH, related_need=need, message=f"Also covers {NEED_LABELS[need]}."))
            continue

        if primary is not None:
            reason = Reason(code=ReasonCode.ALTERNATIVE_FOR, related_need=need, related_product_id=primary[0].product_id,
                            message=f"Closest eligible option for {NEED_LABELS[need]}: "
                                    f"{primary[0].product_name} is not available to you.")
        elif origin == "requested":
            reason = Reason(code=ReasonCode.REQUESTED if requested_pid else ReasonCode.NEED_MATCH, related_need=need,
                            message=f"You asked for {chosen.product_name if requested_pid else NEED_LABELS[need]}.")
        elif origin == "core":
            reason = Reason(code=ReasonCode.SEGMENT_DEFAULT, related_need=need,
                            message=f"Every {SEGMENT_LABELS[segment].lower()} bundle includes {NEED_LABELS[need]}.")
        else:
            reason = Reason(code=ReasonCode.SEGMENT_DEFAULT, related_need=need,
                            message=f"Recommended for businesses like yours: {NEED_LABELS[need]}. You can remove it.")
        item = make_item(chosen, need, is_core=(origin in ("core", "requested")), reasons=[reason])
        if item:
            items[chosen.product_id] = item

    # --- 3. dependencies ------------------------------------------------------------------
    changed = True
    while changed:
        changed = False
        for pid, item in list(items.items()):
            product = catalogue[pid]
            if not product.requires_one_of or any(dep in items for dep in product.requires_one_of):
                continue
            allowed = " or ".join(catalogue[d].product_name for d in product.requires_one_of)
            existing_base = next((b for b in BASE_LINKS if b in items), None)
            if existing_base:
                # The bundle already has an internet line, just not one this product works with.
                # Never add a second line: drop the dependent product and say why.
                del items[pid]
                excluded.append(Exclusion(
                    product_id=pid, product_name=item.product_name,
                    reasons=[Reason(code=ReasonCode.DEPENDENCY_MISSING, related_product_id=pid,
                                    message=f"{item.product_name} works only with {allowed}; your bundle has "
                                            f"{catalogue[existing_base].product_name}.")]))
                changed = True
                continue
            candidates = [catalogue[d] for d in product.requires_one_of if not eligibility_reasons(catalogue[d], profile)]
            candidates.sort(key=lambda p: p.price_min_inr_per_month)
            if candidates:
                base = candidates[0]
                base_item = make_item(base, PRODUCT_NEED[base.product_id], is_core=True, reasons=[Reason(
                    code=ReasonCode.DEPENDENCY_ADDED, related_product_id=pid,
                    message=f"{item.product_name} runs on an internet line at the site, so we added {base.product_name}.")])
                if base_item:
                    items[base.product_id] = base_item
                    changed = True
                    continue
            del items[pid]
            why = eligibility_reasons(catalogue[product.requires_one_of[0]], profile)
            detail = f" ({why[0].message})" if why else ""
            excluded.append(Exclusion(
                product_id=pid, product_name=item.product_name,
                reasons=[Reason(code=ReasonCode.DEPENDENCY_MISSING, related_product_id=pid,
                                message=f"{item.product_name} needs one of {allowed} in the same bundle, "
                                        f"and none of them is available to you{detail}.")]))
            changed = True

    # --- 4. order and price ---------------------------------------------------------------
    ordered = sorted(items.values(), key=lambda i: (not i.is_core, i.product_id))
    pricing, trimmed = price_bundle(ordered, profile)
    for t in trimmed:
        excluded.append(Exclusion(product_id=t.product_id, product_name=t.product_name, reasons=[Reason(
            code=ReasonCode.BUDGET_TRIM, related_product_id=t.product_id,
            message=f"Removed {t.product_name} (Rs {t.monthly_inr:,}/month) to fit your budget. You can add it back later.")]))
    ordered = [i for i in ordered if i.product_id not in {t.product_id for t in trimmed}]

    # --- 5. add-ons -----------------------------------------------------------------------
    add_ons = build_addons(segment, profile, catalogue, {i.product_id for i in ordered}, excluded)

    # --- 6. KYC path + warnings -----------------------------------------------------------
    if profile.gstin_usable:
        kyc_path = "gstin"
    elif profile.has_udyam:
        kyc_path = "udyam_only"
    else:
        kyc_path = "alternative_documents"
    if profile.has_gstin and not profile.gstin_usable:
        warnings.append(f"Your GSTIN is {profile.gstin_status.value} in the GST registry, so GST-only products were "
                        f"left out. You can still buy everything else with your Udyam number or other documents.")
    if any(i.product_id in ("P05", "P06") for i in ordered):
        warnings.append("A leased line needs a site survey before installation; a local Accel Business partner "
                        "will visit to plan the cabling.")
    if any(e.reasons[0].code == ReasonCode.GSTIN_REQUIRED for e in excluded):
        warnings.append("Some items need a GSTIN. Once you register for GST you can add them.")

    return Recommendation(
        segment=segment, segment_label=SEGMENT_LABELS[segment], segment_inferred=segment_inferred,
        items=ordered, excluded=dedupe_exclusions(excluded), add_ons=add_ons, pricing=pricing,
        warnings=warnings, kyc_path=kyc_path)


# ---------------------------------------------------------------------------
# pricing and budget
# ---------------------------------------------------------------------------
def totals(items: list[BundleItem]) -> tuple[int, int, int, int]:
    monthly = sum(i.monthly_inr for i in items)
    setup = sum(i.setup_inr for i in items)
    contract = max((i.min_contract_months for i in items), default=0)
    install = max((i.install_days for i in items), default=0)
    return monthly, setup, contract, install


def price_bundle(items: list[BundleItem], profile: BusinessProfile) -> tuple[Pricing, list[BundleItem]]:
    """Price the bundle; trim optional items if a budget is given and exceeded."""
    trimmed: list[BundleItem] = []
    budget = profile.monthly_budget_inr
    status = BudgetStatus.NO_BUDGET
    gap = 0
    kept = list(items)
    if budget is not None:
        monthly, *_ = totals(kept)
        if monthly <= budget:
            status = BudgetStatus.WITHIN
        else:
            # remove optional items, most expensive first, until it fits
            for candidate in sorted([i for i in kept if not i.is_core], key=lambda i: -i.monthly_inr):
                if totals(kept)[0] <= budget:
                    break
                kept.remove(candidate)
                trimmed.append(candidate)
            monthly, *_ = totals(kept)
            if monthly <= budget:
                status = BudgetStatus.TRIMMED
            else:
                status = BudgetStatus.OVER_MINIMUM
                gap = monthly - budget
    monthly, setup, contract, install = totals(kept)
    return Pricing(monthly_total_inr=monthly, setup_total_inr=setup, contract_months=contract,
                   expected_install_days=install, first_bill_inr=monthly + setup,
                   budget_status=status, budget_gap_inr=gap), trimmed


def reprice(items: list[BundleItem]) -> Pricing:
    """Re-price an edited bundle (quote screen toggles). No budget logic."""
    monthly, setup, contract, install = totals(items)
    return Pricing(monthly_total_inr=monthly, setup_total_inr=setup, contract_months=contract,
                   expected_install_days=install, first_bill_inr=monthly + setup,
                   budget_status=BudgetStatus.NO_BUDGET)


# ---------------------------------------------------------------------------
# add-ons
# ---------------------------------------------------------------------------
def build_addons(segment: Segment, profile: BusinessProfile, catalogue: dict[str, Product],
                 in_bundle: set[str], excluded: list[Exclusion]) -> list[AddOn]:
    add_ons: list[AddOn] = []
    excluded_ids = {e.product_id for e in excluded if e.reasons[0].code != ReasonCode.BUDGET_TRIM}
    base_in_bundle = any(p in in_bundle for p in BASE_LINKS)
    for need in SEGMENT_ADDONS[segment]:
        for pid in preference_list(need, segment, profile):
            product = catalogue[pid]
            if pid in in_bundle or pid in excluded_ids or eligibility_reasons(product, profile):
                continue
            # dependency must be satisfiable by what is already in the bundle
            if product.requires_one_of and not any(d in in_bundle for d in product.requires_one_of):
                continue
            if not base_in_bundle and product.requires_one_of:
                continue
            qty = default_quantity(product, profile, segment)
            if qty <= 0:
                qty = 1
            add_ons.append(AddOn(
                product_id=pid, product_name=product.product_name, category=product.category, unit=product.unit,
                description=product.description, default_quantity=qty, unit_price_inr=product.price_min_inr_per_month,
                monthly_inr=product.price_min_inr_per_month * qty, setup_inr=product.one_time_setup_inr * qty,
                min_contract_months=product.min_contract_months, install_days=product.typical_install_days,
                serves_need=need, why=f"Adds {NEED_LABELS[need]}."))
            break
    return add_ons


def dedupe_exclusions(excluded: list[Exclusion]) -> list[Exclusion]:
    seen: set[str] = set()
    out: list[Exclusion] = []
    for e in excluded:
        if e.product_id not in seen:
            out.append(e); seen.add(e.product_id)
    return out
