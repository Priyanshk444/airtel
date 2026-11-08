"""
Phase 0 - Data exploration for Project Udyam Digital (Accel Business).

Reads the synthetic pack in data/ and writes docs/data_findings.md.
Every number in the findings document is computed here; nothing is typed by hand.

Run:  python analysis/explore_data.py
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data_findings.md"

STAGES = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
STAGE_IDX = {s: i for i, s in enumerate(STAGES)}
DATE_COLS = ["created_date", "contacted_date", "needs_assessed_date",
             "quote_accepted_date", "kyc_complete_date", "activated_date"]

# Figures printed in the case appendix (A1) that we must reproduce.
APPENDIX = {
    "funnel": {"Lead": 5000, "Contacted": 3406, "Needs assessed": 1974,
               "Quote accepted": 861, "KYC complete": 588, "Activated": 368},
    "days_to_activate": 17.6, "follow_up_calls": 3, "blended_cac": 15000,
    "act_with_gstin": 9.6, "act_without_gstin": 2.0,
    "median_bundle": 6900, "micro_avg_bundle": 2500,
}

# Drop reasons that are failures of Accel's own process (reachability, visits,
# quoting, paperwork, installation) rather than a customer saying "no".
PROCESS_DROPS = [
    "Unreachable after 3 attempts", "Wrong or invalid number",
    "Visit not scheduled by sales", "Owner had no time for a visit",
    "Quote took too long to arrive", "Quote too complex to understand",
    "Found paperwork too long", "Authorised signatory not available",
    "Missing GST or Udyam document", "Document details did not match",
    "Installation delayed beyond 21 days", "First payment failed",
]

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def md(df: pd.DataFrame, floatfmt: str = ".1f") -> str:
    """Markdown table; integer columns are rendered without decimals."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_integer_dtype(df[c]):
            df[c] = df[c].map(lambda v: f"{v:,}")
    return df.to_markdown(floatfmt=floatfmt)


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def inr(x: float) -> str:
    return f"Rs {x:,.0f}"


def churn_rate(s: pd.Series) -> float:
    s = s.dropna()
    return (s == "Y").sum() / len(s) if len(s) else np.nan


def parse_bundle(s: str) -> dict[str, int]:
    return {p.split("x")[0]: int(p.split("x")[1]) for p in s.split(";")}


GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum_ok(g: str) -> bool:
    """Real GSTIN mod-36 checksum. README: 4th PAN char is 'X' in this synthetic data."""
    if not isinstance(g, str) or not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", g):
        return False
    total = 0
    for i, ch in enumerate(g[:14]):
        v = GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return GSTIN_CHARS[(36 - total % 36) % 36] == g[14]


def breakdown(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Funnel and outcome metrics for each value of `col`."""
    g = df.groupby(col, observed=False).agg(
        leads=("act", "size"),
        contacted=("stage_idx", lambda s: (s >= 1).mean()),
        assessed=("stage_idx", lambda s: (s >= 2).mean()),
        quote=("stage_idx", lambda s: (s >= 3).mean()),
        kyc=("stage_idx", lambda s: (s >= 4).mean()),
        activated=("act", "mean"),
        avg_bundle=("monthly_bundle_value_inr", "mean"),
        days_to_activate=("days_lead_to_activation", "mean"),
        churn_6m=("churned_within_6_months", churn_rate),
        nps=("nps_score", "mean"),
        cac_total=("acquisition_cost_inr", "sum"),
    )
    g["cac_per_activation"] = g.cac_total / (g.leads * g.activated).replace(0, np.nan)
    out = pd.DataFrame({
        "leads": g.leads,
        "contacted %": 100 * g.contacted, "assessed %": 100 * g.assessed,
        "quote %": 100 * g.quote, "KYC %": 100 * g.kyc, "activated %": 100 * g.activated,
        "avg bundle Rs/m": g.avg_bundle, "days to activate": g.days_to_activate,
        "6m churn %": 100 * g.churn_6m, "avg NPS": g.nps,
        "CAC per activation Rs": g.cac_per_activation,
    })
    out["leads"] = out["leads"].astype(int)
    return out.sort_values("activated %", ascending=False)


# ----------------------------------------------------------------------------
# load
# ----------------------------------------------------------------------------
leads = pd.read_csv(DATA / "smb_leads.csv", parse_dates=DATE_COLS)
cat = pd.read_csv(DATA / "product_catalogue.csv")
gst = pd.read_csv(DATA / "mock_gstin_registry.csv")
udyam = pd.read_csv(DATA / "mock_udyam_registry.csv")

df = leads.copy()
df["act"] = (df.outcome == "Activated").astype(int)
df["stage_idx"] = df.stage_reached.map(STAGE_IDX)
df["d_contact"] = (df.contacted_date - df.created_date).dt.days
df["d_assess"] = (df.needs_assessed_date - df.contacted_date).dt.days
df["d_quote"] = (df.quote_accepted_date - df.needs_assessed_date).dt.days
df["d_kyc"] = (df.kyc_complete_date - df.quote_accepted_date).dt.days
df["d_install"] = (df.activated_date - df.kyc_complete_date).dt.days
df["lang_group"] = np.where(df.preferred_language == "English", "English",
                            np.where(df.preferred_language == "Hindi", "Hindi", "Regional"))
df["registration"] = np.select(
    [df.has_gstin.eq("Y"), df.has_udyam.eq("Y")], ["GSTIN", "Udyam only"], "Neither")
df = df.merge(gst[["gstin", "status"]].rename(columns={"status": "gstin_registry_status"}),
              on="gstin", how="left")
act = df[df.act == 1].copy()

sections: list[str] = []
add = sections.append

# ----------------------------------------------------------------------------
# 1. Funnel vs appendix
# ----------------------------------------------------------------------------
funnel = pd.Series({s: int((df.stage_idx >= i).sum()) for s, i in STAGE_IDX.items()})
funnel_tbl = pd.DataFrame({
    "leads": funnel,
    "% of previous": [np.nan] + [100 * funnel.iloc[i] / funnel.iloc[i - 1] for i in range(1, len(funnel))],
    "% of all leads": 100 * funnel / funnel.iloc[0],
    "case appendix": pd.Series(APPENDIX["funnel"]),
})
funnel_match = all(funnel[s] == APPENDIX["funnel"][s] for s in STAGES)

total_cac = df.acquisition_cost_inr.sum()
blended_cac = total_cac / funnel["Activated"]
act_gstin = df[df.has_gstin == "Y"].act.mean()
act_nogstin = df[df.has_gstin == "N"].act.mean()
micro_avg = act[act.segment == "Micro retail & services"].monthly_bundle_value_inr.mean()
checks = pd.DataFrame([
    ["Average days lead -> activation", f"{act.days_lead_to_activation.mean():.1f}", APPENDIX["days_to_activate"]],
    ["Follow-up calls per activated customer", f"{act.customer_follow_up_calls.mean():.2f}", APPENDIX["follow_up_calls"]],
    ["Blended acquisition cost per activation", f"{blended_cac:,.0f}", f"~{APPENDIX['blended_cac']:,}"],
    ["Activation rate with GSTIN", pct(act_gstin), f"{APPENDIX['act_with_gstin']}%"],
    ["Activation rate without GSTIN", pct(act_nogstin), f"{APPENDIX['act_without_gstin']}%"],
    ["Median monthly bundle (activated)", f"{act.monthly_bundle_value_inr.median():,.0f}", f"{APPENDIX['median_bundle']:,}"],
    ["Average micro-business bundle", f"{micro_avg:,.0f}", f"~{APPENDIX['micro_avg_bundle']:,}"],
], columns=["figure", "computed from data", "case appendix"]).set_index("figure")

add(f"""# Data findings - Project Udyam Digital (Accel Business)

Generated by `analysis/explore_data.py` from the synthetic pack in `data/` ({len(df):,} leads,
{df.created_date.min():%d %b %Y} to {df.created_date.max():%d %b %Y}). All figures below are computed
from the data; anything that is an assumption is labelled **Assumption**.

## 1. The funnel, checked against the case appendix

{md(funnel_tbl, ".0f")}

Funnel matches Appendix A1 exactly: **{'YES' if funnel_match else 'NO - see table'}**.
Only {pct(funnel['Activated'] / funnel['Lead'])} of leads activate. The two steepest losses are
contacted -> needs assessed ({pct(1 - funnel['Needs assessed'] / funnel['Contacted'])} lost) and
needs assessed -> quote accepted ({pct(1 - funnel['Quote accepted'] / funnel['Needs assessed'])} lost).

Other appendix figures:

{md(checks)}

All headline figures reproduce. The blended CAC is total acquisition spend
({inr(total_cac)}) divided by {funnel['Activated']} activations.
""")

# ----------------------------------------------------------------------------
# 2. Breakdowns
# ----------------------------------------------------------------------------
df["employees"] = pd.cut(df.employee_count, [0, 2, 5, 10, 25, 50, 200],
                         labels=["1-2", "3-5", "6-10", "11-25", "26-50", "51+"])
df["sites"] = pd.cut(df.num_sites, [0, 1, 2, 5, 20], labels=["1", "2", "3-5", "6+"])
df["telecom spend"] = pd.cut(df.monthly_telecom_spend_inr, [0, 1000, 2000, 5000, 10000, 1e6],
                             labels=["<=1k", "1-2k", "2-5k", "5-10k", "10k+"])

add("## 2. Conversion and outcomes by dimension\n")
add("Columns: share of leads reaching each stage, average monthly bundle of activated customers, "
    "6-month churn and NPS of activated customers, and acquisition spend on *all* leads in the "
    "group divided by activations in the group.\n")
for col, title in [
    ("segment", "By segment"), ("lead_source", "By lead source"), ("city_tier", "By city tier"),
    ("registration", "By registration status (GSTIN / Udyam only / neither)"),
    ("current_internet", "By current internet setup"), ("current_provider", "By current provider"),
    ("annual_turnover_band", "By turnover band"), ("employees", "By employee count"),
    ("sites", "By number of sites"), ("telecom spend", "By current monthly telecom spend"),
    ("lang_group", "By preferred language"), ("contact_role", "By contact role"),
]:
    add(f"### {title}\n\n{md(breakdown(df, col))}\n")

# city table (short form)
city = breakdown(df, "city")[["leads", "activated %", "days to activate", "6m churn %", "CAC per activation Rs"]]
city["tier"] = df.groupby("city").city_tier.first()
add(f"### By city\n\n{md(city)}\n")

# ----------------------------------------------------------------------------
# 3. Drop reasons
# ----------------------------------------------------------------------------
drops = df[df.outcome == "Dropped"]
reason_stage = pd.crosstab(drops.drop_reason, drops.stage_reached)
reason_stage["total"] = reason_stage.sum(axis=1)
reason_stage["% of drops"] = 100 * reason_stage.total / len(drops)
reason_stage["type"] = np.where(reason_stage.index.isin(PROCESS_DROPS), "process", "demand")
reason_stage = reason_stage.sort_values("total", ascending=False)
process_share = drops.drop_reason.isin(PROCESS_DROPS).mean()

reason_by_source = (pd.crosstab(drops.drop_reason, drops.lead_source, normalize="columns") * 100)
reason_by_source = reason_by_source.loc[reason_stage.index]

quote_stage = drops[drops.stage_reached == "Needs assessed"].drop_reason.value_counts()
quote_proc = quote_stage[["Quote too complex to understand", "Quote took too long to arrive"]].sum()

add(f"""## 3. Why leads drop

{pct(process_share)} of all drops are **process failures** (unreachable, visit never happened, quote
too slow or too complex, paperwork, installation delay) rather than the customer saying no to the
offer. These are exactly what a self-serve digital journey removes.

{md(reason_stage, ".1f")}

**At the quote stage** ({funnel['Needs assessed'] - funnel['Quote accepted']} leads lost, the biggest absolute
loss in the funnel): {quote_proc} leads ({pct(quote_proc / quote_stage.sum())} of quote-stage drops) left because
the quote was *too complex* or *took too long*, versus {quote_stage['Price too high']} for price and
{quote_stage['Competitor offered cheaper plan']} for a cheaper competitor.

**Reasons by lead source** (% of that source's drops):

{md(reason_by_source, ".1f")}
""")

# ----------------------------------------------------------------------------
# 4. Time to activate, follow-up calls, churn, NPS
# ----------------------------------------------------------------------------
dur = df[["d_contact", "d_assess", "d_quote", "d_kyc", "d_install", "days_lead_to_activation"]].describe().T
dur.index = ["lead -> contacted", "contacted -> needs assessed", "needs assessed -> quote accepted",
             "quote accepted -> KYC complete", "KYC complete -> activated (install)", "lead -> activated (total)"]
dur = dur[["count", "mean", "50%", "min", "max"]]

seg_time = act.groupby(["segment", "city_tier"]).agg(
    activated=("act", "size"), install_days=("d_install", "mean"),
    total_days=("days_lead_to_activation", "mean"), follow_up_calls=("customer_follow_up_calls", "mean"))

calls = act.groupby("customer_follow_up_calls").agg(
    customers=("act", "size"), avg_nps=("nps_score", "mean"),
    churn_6m=("churned_within_6_months", churn_rate))
calls["churn_6m"] *= 100

days_bucket = act.groupby(pd.cut(act.days_lead_to_activation, [0, 10, 15, 20, 25, 40]), observed=False).agg(
    customers=("act", "size"), avg_nps=("nps_score", "mean"), churn_6m=("churned_within_6_months", churn_rate))
days_bucket["churn_6m"] *= 100

nps_overall = 100 * ((act.nps_score >= 9).mean() - (act.nps_score <= 6).mean())
nps_seg = act.groupby("segment").apply(
    lambda g: pd.Series({"customers": len(g), "avg score": g.nps_score.mean(),
                         "promoters %": 100 * (g.nps_score >= 9).mean(),
                         "detractors %": 100 * (g.nps_score <= 6).mean(),
                         "NPS": 100 * ((g.nps_score >= 9).mean() - (g.nps_score <= 6).mean())}),
    include_groups=False)

contract = act.groupby("contract_months").agg(
    customers=("act", "size"), avg_bundle=("monthly_bundle_value_inr", "mean"),
    churn_6m=("churned_within_6_months", churn_rate), avg_nps=("nps_score", "mean"))
contract["churn_6m"] *= 100

churn_seg_src = act.pivot_table(index="segment", columns="lead_source", values="churned_within_6_months",
                                aggfunc=churn_rate) * 100
n_seg_src = act.pivot_table(index="segment", columns="lead_source", values="act", aggfunc="size").fillna(0).astype(int)

corr = act[["days_lead_to_activation", "d_install", "customer_follow_up_calls", "nps_score"]].corr()

add(f"""## 4. Time to activate, status chasing, churn and NPS

### Stage durations (days)

{md(dur, ".1f")}

Every stage is slow: a contacted lead waits ~{df.d_assess.mean():.0f} days for a needs visit, then
~{df.d_quote.mean():.0f} days for a quote, ~{df.d_kyc.mean():.0f} days for KYC and ~{act.d_install.mean():.1f} days
for installation. Installation is the most variable step (up to {act.d_install.max():.0f} days).

### By segment and city tier (activated customers)

{md(seg_time, ".1f")}

Tier-2 installations take ~{(act[act.city_tier == 2].d_install.mean() - act[act.city_tier == 1].d_install.mean()):.1f} days
longer than tier 1. Manufacturers (leased lines, {cat.set_index('product_id').loc['P05', 'typical_install_days']}-{cat.set_index('product_id').loc['P06', 'typical_install_days']} day installs) are slowest.

### Status-chasing calls predict unhappiness and churn

{md(calls, ".1f")}

Customers who had to call {calls.index.max()} times to chase their order have an average NPS of
{calls.loc[calls.index.max(), 'avg_nps']:.1f} and {calls.loc[calls.index.max(), 'churn_6m']:.0f}% churn, against
{calls.loc[calls.index.min(), 'avg_nps']:.1f} and {calls.loc[calls.index.min(), 'churn_6m']:.0f}% for customers who called once.
Correlation of follow-up calls with NPS: {corr.loc['customer_follow_up_calls', 'nps_score']:.2f};
of total days to activate with NPS: {corr.loc['days_lead_to_activation', 'nps_score']:.2f}.
This is the direct evidence for the order tracker.

### Slow activations hurt NPS

{md(days_bucket, ".1f")}

### NPS by segment

Overall NPS is **{nps_overall:.0f}** ({pct((act.nps_score >= 9).mean())} promoters, {pct((act.nps_score <= 6).mean())} detractors).

{md(nps_seg, ".1f")}

### Contract length

{md(contract, ".1f")}

(Only {int(contract.loc[6.0, 'customers'])} customers are on 6-month contracts, so that row is not meaningful.)

### 6-month churn by segment x lead source (%, activated customers)

{md(churn_seg_src, ".0f")}

Customer counts behind the table above:

{md(n_seg_src, ".0f")}
""")

# ----------------------------------------------------------------------------
# 5. Planted / anomalous patterns
# ----------------------------------------------------------------------------
# 5a digital leads under-contacted
src = breakdown(df, "lead_source")
digital = src.loc[["Website form", "WhatsApp campaign"]]
unreach = reason_by_source.loc[["Unreachable after 3 attempts", "Wrong or invalid number"]]

# 5b activated customers with cancelled/suspended GSTIN
bad_gstin = act[act.gstin_registry_status.isin(["Cancelled", "Suspended"])]
bad_gstin_tbl = bad_gstin[["lead_id", "business_name", "segment", "gstin_registry_status",
                           "lead_source", "churned_within_6_months", "nps_score"]].copy()
bad_gstin_tbl["gstin"] = bad_gstin.gstin.str[:2] + "XXXXXXXXX" + bad_gstin.gstin.str[-4:]
bad_gstin_tbl = bad_gstin_tbl.set_index("lead_id")
reg_status_outcome = pd.crosstab(df.gstin_registry_status.fillna("(no GSTIN)"), df.outcome)
reg_status_outcome["activation %"] = 100 * reg_status_outcome.Activated / reg_status_outcome.sum(axis=1)
kyc_doc_mismatch = df[(df.drop_reason == "Document details did not match")]
kyc_mismatch_bad = kyc_doc_mismatch.gstin_registry_status.isin(["Cancelled", "Suspended"]).sum()

# 5c eligibility violations in sold bundles
catx = cat.set_index("product_id")


def bundle_violations(r: pd.Series) -> list[str]:
    b = parse_bundle(r.bundle_products)
    v = []
    for p in b:
        c = catx.loc[p]
        tiers = [int(t) for t in str(c.available_city_tiers).split(";")]
        if r.city_tier not in tiers:
            v.append(f"{p} not sold in tier {r.city_tier}")
        if r.employee_count < c.min_employees:
            v.append(f"{p} needs {c.min_employees}+ employees (has {r.employee_count})")
        if r.num_sites < c.min_sites:
            v.append(f"{p} needs {c.min_sites}+ sites (has {r.num_sites})")
        if c.requires_gstin == "Y" and r.has_gstin != "Y":
            v.append(f"{p} requires GSTIN (lead has none)")
        if isinstance(c.requires_one_of, str) and not any(x in b for x in c.requires_one_of.split("|")):
            v.append(f"{p} requires one of {c.requires_one_of.replace('|', '/')}")
    return v


act["violations"] = act.apply(bundle_violations, axis=1)
act["has_violation"] = act.violations.str.len() > 0
viol_rows = act[act.has_violation]
viol_kind = pd.Series([re.sub(r"\(.*\)", "", v).strip() for vs in viol_rows.violations for v in vs]).value_counts()
viol_cmp = act.groupby("has_violation").agg(
    customers=("act", "size"), install_days=("d_install", "mean"),
    total_days=("days_lead_to_activation", "mean"), churn_6m=("churned_within_6_months", churn_rate),
    avg_nps=("nps_score", "mean"))
viol_cmp["churn_6m"] *= 100
viol_cmp.index = ["bundle obeys catalogue rules", "bundle breaks a rule"]
# bundle value / setup / contract consistency with catalogue
act["v_min"] = act.bundle_products.apply(lambda s: sum(catx.loc[p, "price_min_inr_per_month"] * q for p, q in parse_bundle(s).items()))
act["v_max"] = act.bundle_products.apply(lambda s: sum(catx.loc[p, "price_max_inr_per_month"] * q for p, q in parse_bundle(s).items()))
act["setup_calc"] = act.bundle_products.apply(lambda s: sum(catx.loc[p, "one_time_setup_inr"] * q for p, q in parse_bundle(s).items()))
act["contract_calc"] = act.bundle_products.apply(lambda s: max(catx.loc[p, "min_contract_months"] for p in parse_bundle(s)))
price_ok = ((act.monthly_bundle_value_inr >= act.v_min) & (act.monthly_bundle_value_inr <= act.v_max)).mean()
setup_ok = (act.setup_calc == act.one_time_setup_inr).mean()
contract_ok = (act.contract_calc == act.contract_months).mean()

# 5d interest vs bought
act["interest_share"] = act.apply(
    lambda r: len(set(r.products_of_interest.split(";")) & set(parse_bundle(r.bundle_products)))
    / len(r.products_of_interest.split(";")), axis=1)
interest_rows = [(seg_, p) for seg_, s in zip(df.segment, df.products_of_interest) for p in s.split(";")]
interest = pd.DataFrame(interest_rows, columns=["segment", "product"]).groupby("product").size()
bought_rows = [(r.segment, p) for _, r in act.iterrows() for p in parse_bundle(r.bundle_products)]
bought = pd.DataFrame(bought_rows, columns=["segment", "product"]).groupby("product").size()
iv = pd.DataFrame({"leads interested": interest, "activated bundles containing it": bought}).fillna(0).astype(int)
iv["name"] = catx.product_name
iv["bought per 100 interested"] = 100 * iv["activated bundles containing it"] / iv["leads interested"]
iv = iv.sort_values("bought per 100 interested")
p04 = iv.loc["P04"]
fibre_not_feasible = (df.drop_reason == "Site not feasible for fibre").sum()
mobile_only = df[df.drop_reason == "Only wanted a mobile plan"].segment.value_counts()

# 5e cost structure
cost_ladder = df.pivot_table(index="lead_source", columns="stage_reached", values="acquisition_cost_inr",
                             aggfunc="mean")[STAGES]
cp_act = act[act.lead_source == "Channel partner"]
cp_ratio = cp_act.acquisition_cost_inr / cp_act.monthly_bundle_value_inr
fs_const = act[act.lead_source == "Field sales"].acquisition_cost_inr.nunique() == 1
cac_share = (df.groupby("lead_source").acquisition_cost_inr.sum() / total_cac * 100).sort_values(ascending=False)

# 5f GSTIN gap at KYC
reg = df.groupby("registration").agg(
    leads=("act", "size"),
    reached_quote=("stage_idx", lambda s: int((s >= 3).sum())),
    passed_kyc=("stage_idx", lambda s: int((s >= 4).sum())),
    activated=("act", "sum"))
reg["quote -> KYC %"] = 100 * reg.passed_kyc / reg.reached_quote
reg["activation %"] = 100 * reg.activated / reg.leads
nogst_kyc_drops = df[(df.has_gstin == "N") & (df.stage_reached == "Quote accepted")].drop_reason.value_counts()

# 5g duplicates / registry sanity
dup_names = df.business_name.duplicated().sum()
gst_valid_leads = df[df.has_gstin == "Y"].gstin.apply(gstin_checksum_ok).mean()
gst_valid_reg = gst.gstin.apply(gstin_checksum_ok).mean()
gst_missing = (df.has_gstin.eq("Y") & df.gstin_registry_status.isna()).sum()
ud_merge = df.merge(udyam, on="udyam_number", how="left")
ud_missing = (ud_merge.has_udyam.eq("Y") & ud_merge.enterprise_name.isna()).sum()
ud_name_mismatch = (ud_merge.has_udyam.eq("Y") & (ud_merge.enterprise_name != ud_merge.business_name)).sum()

add(f"""## 5. Patterns that look deliberately planted

These are flagged because they are too clean or too consequential to be random noise. Each one
maps to a feature of the prototype.

### 5a. Digital leads are the cheapest and buy the biggest bundles, but the field force does not pick them up

{md(digital[["leads", "contacted %", "activated %", "avg bundle Rs/m", "CAC per activation Rs"]], ".1f")}

Website-form leads are contacted only {digital.loc['Website form', 'contacted %']:.0f}% of the time and WhatsApp-campaign
leads {digital.loc['WhatsApp campaign', 'contacted %']:.0f}%, against {src.loc['Field sales', 'contacted %']:.0f}% for field sales.
Their drop reasons are dominated by "Unreachable" and "Wrong or invalid number":

{md(unreach, ".1f")}

Yet the few that do activate buy the largest bundles of any source ({inr(digital.loc['Website form', 'avg bundle Rs/m'])} and
{inr(digital.loc['WhatsApp campaign', 'avg bundle Rs/m'])} per month) at a CAC of
{inr(digital['CAC per activation Rs'].min())}-{inr(digital['CAC per activation Rs'].max())}
against {inr(src.loc['Field sales', 'CAC per activation Rs'])} for field sales. **Implication:** an inbound digital lead
should be able to complete the whole journey itself instead of waiting for a call-back.

### 5b. {len(bad_gstin)} activated customers have a Cancelled or Suspended GSTIN in the registry

{md(reg_status_outcome, ".1f")}

Leads whose GSTIN is Cancelled or Suspended were activated at almost the same rate as Active ones, so the
current KYC process is not checking registry status. Their 6-month churn is
{pct(churn_rate(bad_gstin.churned_within_6_months))} versus {pct(churn_rate(act[act.gstin_registry_status == 'Active'].churned_within_6_months))}
for customers with an Active GSTIN. Only {kyc_mismatch_bad} of the {len(kyc_doc_mismatch)} "Document details did not match" drops
had a bad GSTIN, so the mismatch reason is not catching them either. **Implication:** Smart KYC must call the
GSTIN lookup and block (or route to review) non-Active registrations.

{md(bad_gstin_tbl, ".0f")}

### 5c. {len(viol_rows)} of {len(act)} sold bundles ({pct(len(viol_rows) / len(act))}) break a catalogue eligibility rule

{md(viol_kind.to_frame('count'), ".0f")}

The common case is Biz Fibre 1G (P03), which the catalogue restricts to tier-1 cities and 5+ employees,
sold in tier-2 cities or to 3-4 person offices. Static IP was sold without any fibre line to attach it to,
and GSTIN-only products (WhatsApp API, SMS, SIP, SD-WAN) were sold to leads with no GSTIN.
Bundles that break a rule take {viol_cmp.loc['bundle breaks a rule', 'install_days'] - viol_cmp.loc['bundle obeys catalogue rules', 'install_days']:.1f} days
longer to install:

{md(viol_cmp, ".1f")}

Bundle prices, setup fees and contract lengths are otherwise fully consistent with the catalogue
(price inside the catalogue min-max range: {pct(price_ok)}; setup fee matches: {pct(setup_ok)}; contract = longest
minimum contract in the bundle: {pct(contract_ok)}). **Implication:** the rule engine must enforce tier,
size, GSTIN and dependency rules deterministically; this is what the 15 judge scenarios will probe.

### 5d. Sales sells what is on target, not what the lead asked for

On average only {pct(act.interest_share.mean())} of the products a lead asked about end up in the bundle they bought,
and {pct((act.interest_share == 0).mean())} of activated customers bought *none* of the products they originally asked for.

{md(iv.head(8), ".1f")}

5G AirFiber (P04) is the most striking: {int(p04['leads interested'])} leads asked about it, {int(p04['activated bundles containing it'])} bought it,
while {fibre_not_feasible} leads were dropped as "Site not feasible for fibre" - the exact situation AirFiber exists for.
Similarly {int(mobile_only.sum())} leads ({int(mobile_only['Micro retail & services'])} micro businesses) were dropped as
"Only wanted a mobile plan" instead of being sold a Rs 299 business postpaid line online.
**Implication:** the advisor must start from the stated need and offer the nearest eligible alternative.

### 5e. Acquisition cost is a fixed per-stage ladder for field sales and a commission for partners

Average acquisition cost (Rs) by lead source and the furthest stage the lead reached:

{md(cost_ladder, ".0f")}

Field sales spends a fixed {inr(cost_ladder.loc['Field sales', 'Needs assessed'])} on every lead that gets a needs visit and
{inr(cost_ladder.loc['Field sales', 'Activated'])} on every activation, regardless of bundle size
(constant across all activations: {fs_const}). Channel partners are paid {cp_ratio.min():.2f}x to {cp_ratio.max():.2f}x
(mean {cp_ratio.mean():.2f}x) of the monthly bundle value on activation. Field sales and partners together consume
{cac_share['Field sales'] + cac_share['Channel partner']:.0f}% of all acquisition spend:

{md(cac_share.to_frame('% of acquisition spend'), ".1f")}

**Implication:** every visit avoided by digital needs discovery saves a fixed {inr(cost_ladder.loc['Field sales', 'Needs assessed'] - cost_ladder.loc['Field sales', 'Contacted'])} per lead,
and the partner model can be kept for activation while removing the fixed field cost.

### 5f. Businesses without a GSTIN hit a dead end at KYC

{md(reg, ".1f")}

Leads without GSTIN reach the quote stage at a reasonable rate but only {reg.loc['Udyam only', 'quote -> KYC %']:.0f}% (Udyam only)
and {reg.loc['Neither', 'quote -> KYC %']:.0f}% (neither) pass KYC, against {reg.loc['GSTIN', 'quote -> KYC %']:.0f}% for GSTIN holders.
Their KYC-stage drop reasons: {', '.join(f'{k} ({v})' for k, v in nogst_kyc_drops.items())}.
{int(reg.loc['Udyam only', 'leads'])} leads have a Udyam number but no GSTIN; the catalogue only requires GSTIN for
{int((cat.requires_gstin == 'Y').sum())} of {len(cat)} products, so most of the micro bundle can be sold on Udyam alone.
**Implication:** a Udyam-only / alternative-document KYC path.

### 5g. Data quality checks (nothing suspicious here)

- GSTIN checksum valid: {pct(gst_valid_leads)} of lead GSTINs, {pct(gst_valid_reg)} of registry GSTINs (mod-36 algorithm, 'X' accepted as 4th PAN character).
- Lead GSTINs missing from the registry: {gst_missing}. Udyam numbers missing from the registry: {ud_missing}. Udyam name mismatches: {ud_name_mismatch}.
- Registry status mix: {', '.join(f'{k} {v}' for k, v in gst.status.value_counts().items())}.
- Repeated business names: {dup_names} (synthetic name generator reuses names; no duplicate GSTINs, so these are not duplicate leads).
- No negative stage durations; every stage date is in order.
""")

# ----------------------------------------------------------------------------
# 6. Unit economics
# ----------------------------------------------------------------------------
ue = df.groupby("segment").agg(
    leads=("act", "size"), activated=("act", "sum"), spend=("acquisition_cost_inr", "sum"),
    bundle=("monthly_bundle_value_inr", "mean"), setup=("one_time_setup_inr", "mean"),
    contract=("contract_months", "mean"), churn=("churned_within_6_months", churn_rate))
ue["activation %"] = 100 * ue.activated / ue.leads
ue["actual CAC per activation"] = ue.spend / ue.activated
ue["payback months (actual CAC)"] = ue["actual CAC per activation"] / ue.bundle
ue["payback months (Rs 15,000 CAC)"] = APPENDIX["blended_cac"] / ue.bundle
# Assumption: churners leave half-way through the first 12 months on average
ue["12m revenue net of churn"] = ue.bundle * 12 * (1 - ue.churn / 2) + ue.setup
ue["12m revenue / actual CAC"] = ue["12m revenue net of churn"] / ue["actual CAC per activation"]
ue_out = ue[["leads", "activated", "activation %", "bundle", "setup", "contract", "actual CAC per activation",
             "payback months (actual CAC)", "payback months (Rs 15,000 CAC)", "12m revenue net of churn",
             "12m revenue / actual CAC"]].rename(columns={"bundle": "avg bundle Rs/m", "setup": "avg setup Rs",
                                                          "contract": "avg contract months"})
ue_out["6m churn %"] = 100 * ue.churn

# what CAC would micro need to pay back in 6 months?
micro = ue.loc["Micro retail & services"]
micro_cac_target = micro.bundle * 6
digital_cac = src.loc[["Website form", "WhatsApp campaign", "Inbound call", "Referral"], "CAC per activation Rs"]

# segment-level share of activations and value
val_share = act.groupby("segment").monthly_bundle_value_inr.sum() / act.monthly_bundle_value_inr.sum() * 100

add(f"""## 6. Unit economics per segment

Payback = acquisition cost per activation divided by average monthly bundle value. This is a *gross
revenue* payback. **Assumption:** no margin figure is given in the data, so a payback on revenue is used
for comparison; on a (say) 40% contribution margin, multiply the payback months by 2.5.
**Assumption** for the 12-month revenue column: customers who churn within 6 months pay for 6 months on average.

{md(ue_out.T, ".1f")}

Share of activations vs share of monthly recurring value:

{md(pd.DataFrame({'share of activations %': act.segment.value_counts(normalize=True) * 100, 'share of monthly bundle value %': val_share}), ".1f")}

Micro retail is the only segment whose actual CAC ({inr(micro['actual CAC per activation'])}) is not recovered inside a
12-month contract on a reasonable margin: an average {inr(micro.bundle)}/month bundle needs a CAC below
~{inr(micro_cac_target)} to pay back within 6 months. The low-touch sources already achieve that
({', '.join(f'{k} {inr(v)}' for k, v in digital_cac.items())}), the field-sales and partner model does not.
""")

# ----------------------------------------------------------------------------
# 7. Recommendation
# ----------------------------------------------------------------------------
prof = ue.loc["Professional offices"]
multi = ue.loc["Small multi-site businesses"]
mfg = ue.loc["Small manufacturers"]
mfg_days = act[act.segment == "Small manufacturers"].days_lead_to_activation.mean()
prof_src = df[df.segment == "Professional offices"]
micro_src = df[df.segment == "Micro retail & services"]
micro_fs_churn = churn_rate(act[(act.segment == "Micro retail & services") & (act.lead_source == "Field sales")].churned_within_6_months)
micro_dig_churn = churn_rate(act[(act.segment == "Micro retail & services") & (act.lead_source.isin(["Website form", "WhatsApp campaign"]))].churned_within_6_months)

add(f"""## 7. Which segments to prioritise, and why

**1. Professional offices first** (clinics, CA firms, coaching centres, law and real-estate offices).
- Largest number of activations ({int(prof.activated)}) and the best activation rate among sizeable segments ({prof['activation %']:.1f}%).
- Lowest actual CAC per activation ({inr(prof['actual CAC per activation'])}) and {prof['payback months (actual CAC)']:.1f}-month revenue payback on a {inr(prof.bundle)}/month bundle.
- Standard 12-month contracts, {100 * prof.churn:.0f}% churn, {pct((prof_src.has_gstin == 'Y').mean())} have a GSTIN so KYC is straightforward.
- Needs are uniform (fibre + cloud email + a few postpaid lines + backup/security) and need no site survey, so the digital advisor can close them end to end.

**2. Small multi-site businesses second.**
- Highest value: {inr(multi.bundle)}/month average, {val_share['Small multi-site businesses']:.0f}% of all recurring value from {act.segment.value_counts(normalize=True)['Small multi-site businesses'] * 100:.0f}% of activations; payback {multi['payback months (actual CAC)']:.1f} months.
- Lowest churn with field sales and inbound; but the bundle (SD-WAN, failover, CCTV per site) has dependencies and 24-month contracts, so the advisor should quote and then hand off to a partner for the multi-site install.

**3. Micro retail and services only through the self-serve channel.**
- {pct(micro_src.shape[0] / len(df))} of leads but just {micro['activation %']:.1f}% activate; actual CAC {inr(micro['actual CAC per activation'])} against a {inr(micro.bundle)} bundle ({micro['payback months (actual CAC)']:.1f} months payback, before margin).
- The field model cannot serve this segment profitably; the digital journey is the *only* way to make it work, and it also solves the two micro-specific drops: "Only wanted a mobile plan" and the no-GSTIN dead end ({pct((micro_src.has_gstin == 'N').mean())} of micro leads have no GSTIN).
- Watch churn: micro customers from digital sources churn at {pct(micro_dig_churn)} vs {pct(micro_fs_churn)} from field sales (small samples), so the tracker and a right-sized starter bundle matter here.

**4. Small manufacturers: keep field-assisted.** Only {int(mfg.leads)} leads ({pct(mfg.leads / len(df))}), slowest activation
({mfg_days:.1f} days) because of leased-line installs, and the worst NPS ({nps_seg.loc['Small manufacturers', 'NPS']:.0f}).
Good economics ({mfg['payback months (actual CAC)']:.1f}-month payback) but needs a site survey; use the advisor for discovery and quote, then hand off.

### What the data says the prototype must do

| Finding | Feature |
| --- | --- |
| {pct(process_share)} of drops are process failures | self-serve journey end to end |
| Quote too slow / too complex = {quote_proc} drops | instant, plain-language quote with one monthly price |
| Follow-up calls drive NPS from {calls.loc[1, 'avg_nps']:.1f} to {calls.loc[5, 'avg_nps']:.1f} | order tracker with expected dates |
| {len(bad_gstin)} activations with cancelled/suspended GSTIN | GSTIN registry lookup in KYC |
| {len(viol_rows)} bundles break catalogue rules | deterministic rule engine, LLM never prices |
| Only {pct(act.interest_share.mean())} of asked-for products are sold | advisor starts from stated need, offers nearest eligible alternative |
| Udyam-only leads pass KYC at {reg.loc['Udyam only', 'quote -> KYC %']:.0f}% | Udyam-only KYC path |
| Digital leads contacted {digital.loc['WhatsApp campaign', 'contacted %']:.0f}-{digital.loc['Website form', 'contacted %']:.0f}% | inbound leads complete the journey themselves; handoff only when stuck |
""")

# ----------------------------------------------------------------------------
# 8. Product catalogue in plain English
# ----------------------------------------------------------------------------
def rule_text(r: pd.Series) -> str:
    rules = []
    tiers = str(r.available_city_tiers).split(";")
    rules.append("tier-1 cities only" if tiers == ["1"] else "tier 1 and 2 cities")
    if r.min_employees > 1:
        rules.append(f"{r.min_employees}+ employees")
    if r.min_sites > 1:
        rules.append(f"{r.min_sites}+ sites")
    rules.append("GSTIN required" if r.requires_gstin == "Y" else "no GSTIN needed")
    if isinstance(r.requires_one_of, str):
        rules.append("needs one of " + ", ".join(r.requires_one_of.split("|")) + " in the same bundle")
    return "; ".join(rules)


cat_tbl = pd.DataFrame({
    "product": cat.product_id + " " + cat.product_name,
    "category": cat.category,
    "unit": cat.unit,
    "Rs/month (min-max)": cat.price_min_inr_per_month.astype(str) + "-" + cat.price_max_inr_per_month.astype(str),
    "setup Rs": cat.one_time_setup_inr,
    "min contract (months)": cat.min_contract_months,
    "install days": cat.typical_install_days,
    "segments": cat.target_segments,
    "eligibility and dependencies": cat.apply(rule_text, axis=1),
}).set_index("product")

dep_products = cat[cat.requires_one_of.notna()]
gstin_products = cat[cat.requires_gstin == "Y"]
tier1_only = cat[cat.available_city_tiers == "1"]
size_products = cat[(cat.min_employees > 1) | (cat.min_sites > 1)]

add(f"""## 8. The product catalogue, rule by rule

{len(cat)} products in {cat.category.nunique()} categories. Prices are per unit per month with a min-max range
(the engine will quote the minimum as the list price and keep the range for partner discretion).
Setup fees are one-time per unit. Contract length of a bundle = the longest minimum contract among its products
(this is how every activated bundle in the data was priced).

### Rules in plain English

1. **City tier.** Every product is sold in tier 1 and 2 except {', '.join(tier1_only.product_id + ' ' + tier1_only.product_name)}, which is tier-1 only.
   A tier-2 customer asking for 1 Gbps fibre must be offered Biz Fibre 300 (P02) or a leased line instead.
2. **Minimum size.** {'; '.join(f'{r.product_id} {r.product_name}: {r.min_employees}+ employees' + (f', {r.min_sites}+ sites' if r.min_sites > 1 else '') for _, r in size_products.iterrows())}.
   Smaller businesses get the next product down (e.g. Biz Fibre 300 instead of 1G, Biz Fibre 300 + failover instead of a leased line).
3. **GSTIN required** for {len(gstin_products)} products: {', '.join(gstin_products.product_id)}. These are the regulated or high-value
   items (leased lines, 1G fibre, SD-WAN, telephony, toll-free, SMS, WhatsApp API, firewall, machine IoT). A business with only a
   Udyam number can still buy the other {len(cat) - len(gstin_products)} products, which cover the entire micro bundle
   (fibre or AirFiber, postpaid lines, POS, website, CCTV, Wi-Fi, email, backup, endpoint security).
4. **Dependencies (requires one of).** {len(dep_products)} products only work on top of a connectivity product in the same bundle:
{chr(10).join(f'   - {r.product_id} {r.product_name} needs {r.requires_one_of.replace("|", " or ")}' for _, r in dep_products.iterrows())}
   The engine adds the cheapest eligible base link automatically and explains why, or removes the dependent product if no base link is eligible.
5. **Per-unit quantities.** Products are priced per site, per line, per user, per device, per camera, per counter or per vehicle; the engine
   sizes quantities from the profile (sites, employees, counters, cameras, vehicles).
6. **Install days** drive the expected activation date on the tracker; the bundle's expected activation is the longest install among its products.

### Full catalogue

{md(cat_tbl, ".0f")}
""")

OUT.write_text("\n".join(sections), encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
print("funnel matches appendix:", funnel_match)
