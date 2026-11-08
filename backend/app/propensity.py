"""
Explainable propensity score: which leads should a partner call first?

A logistic regression on smb_leads.csv using only facts known at lead creation (no funnel dates,
no outcomes). Trained once at startup on a stratified 80/20 split; the held-out metrics are
reported as-is. Coefficients on standardised features give the top factors, and each lead's score
comes with its own top contributing reasons.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from .engine.catalogue import data_dir

SEED = 42
CATEGORICAL = ["lead_source", "segment", "city_tier", "has_gstin", "has_udyam", "current_internet",
               "current_provider", "annual_turnover_band", "contact_role", "lang_group"]
NUMERIC = ["log_employees", "log_sites", "log_spend", "n_interest"]

FRIENDLY = {
    "lead_source": "Lead source", "segment": "Segment", "city_tier": "City tier", "has_gstin": "Has GSTIN",
    "has_udyam": "Has Udyam", "current_internet": "Current internet", "current_provider": "Current provider",
    "annual_turnover_band": "Turnover", "contact_role": "Contact role", "lang_group": "Language",
    "log_employees": "Number of employees", "log_sites": "Number of sites", "log_spend": "Current telecom spend",
    "n_interest": "Products asked about",
}


def _features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in CATEGORICAL[:-1]:
        out[c] = df[c].astype(str)
    out["lang_group"] = np.where(df.preferred_language == "English", "English", np.where(df.preferred_language == "Hindi", "Hindi", "Regional"))
    out["log_employees"] = np.log1p(df.employee_count)
    out["log_sites"] = np.log1p(df.num_sites)
    out["log_spend"] = np.log1p(df.monthly_telecom_spend_inr)
    out["n_interest"] = df.products_of_interest.fillna("").str.count(";") + 1
    return out


class PropensityModel:
    def __init__(self) -> None:
        leads = pd.read_csv(data_dir() / "smb_leads.csv")
        self.leads = leads
        X = _features(leads)
        y = (leads.outcome == "Activated").astype(int).values
        self.columns = pd.get_dummies(X, columns=CATEGORICAL, drop_first=True).columns
        Xd = self._design(X)
        X_tr, X_te, y_tr, y_te, idx_tr, idx_te = train_test_split(Xd, y, leads.index, test_size=0.2, stratify=y, random_state=SEED)
        self.mu, self.sd = X_tr.mean(axis=0), X_tr.std(axis=0) + 1e-9
        self.model = LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced", random_state=SEED)
        self.model.fit((X_tr - self.mu) / self.sd, y_tr)
        self.test_index = idx_te
        p = self.model.predict_proba((X_te - self.mu) / self.sd)[:, 1]
        self.metrics = self._metrics(y_te, p)
        self.scores = self.model.predict_proba((Xd - self.mu) / self.sd)[:, 1]

    def _design(self, X: pd.DataFrame) -> np.ndarray:
        d = pd.get_dummies(X, columns=CATEGORICAL, drop_first=True).reindex(columns=self.columns, fill_value=0)
        return d.values.astype(float)

    @staticmethod
    def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
        order = np.argsort(-p)
        n = len(y)
        top10 = order[: max(1, n // 10)]
        top20 = order[: max(1, n // 5)]
        base = float(y.mean())
        return {
            "test_leads": int(n), "activation_rate_baseline": round(base, 4),
            "roc_auc": round(float(roc_auc_score(y, p)), 3),
            "average_precision": round(float(average_precision_score(y, p)), 3),
            "precision_top10pct": round(float(y[top10].mean()), 3), "lift_top10pct": round(float(y[top10].mean() / base), 2),
            "recall_top20pct": round(float(y[top20].sum() / max(y.sum(), 1)), 3),
            "accuracy_at_0_5": round(float(((p >= 0.5) == y).mean()), 3),
            "note": "Held-out 20% stratified split, seed 42. Accuracy at 0.5 is low by design (balanced class weights); "
                    "use the ranking metrics. Only lead-creation facts are used as features.",
        }

    def factors(self, top: int = 12) -> list[dict[str, Any]]:
        coef = self.model.coef_[0]
        rows = []
        for name, c in zip(self.columns, coef):
            base, _, level = name.partition("_") if name.split("_")[0] in FRIENDLY else (name, "", "")
            # reconstruct "feature=level" for one-hot columns
            feat = next((f for f in CATEGORICAL if name.startswith(f + "_")), None)
            if feat:
                label = f"{FRIENDLY[feat]} = {name[len(feat) + 1:]}"
            else:
                label = FRIENDLY.get(name, name)
            rows.append({"factor": label, "weight": round(float(c), 3), "direction": "raises" if c > 0 else "lowers"})
        rows.sort(key=lambda r: -abs(r["weight"]))
        return rows[:top]

    def rank(self, state: str | None = None, city: str | None = None, segment: str | None = None,
             limit: int = 25, only_open: bool = True) -> list[dict[str, Any]]:
        df = self.leads.assign(score=self.scores)
        if only_open:
            df = df[df.outcome != "Activated"]
        if state:
            df = df[df.state.str.lower() == state.lower()]
        if city:
            df = df[df.city.str.lower() == city.lower()]
        if segment:
            df = df[df.segment == segment]
        df = df.sort_values("score", ascending=False).head(limit)
        Xd = (self._design(_features(df)) - self.mu) / self.sd
        contrib = Xd * self.model.coef_[0]
        out = []
        for (i, row), c in zip(df.iterrows(), contrib):
            top = np.argsort(-np.abs(c))[:3]
            reasons = []
            for j in top:
                name = self.columns[j]
                feat = next((f for f in CATEGORICAL if name.startswith(f + "_")), None)
                label = f"{FRIENDLY[feat]} {name[len(feat) + 1:]}" if feat else FRIENDLY.get(name, name)
                reasons.append(("+" if c[j] > 0 else "-") + " " + label)
            out.append({
                "lead_id": row.lead_id, "business_name": row.business_name, "business_type": row.business_type, "segment": row.segment,
                "city": row.city, "state": row.state, "lead_source": row.lead_source, "stage_reached": row.stage_reached,
                "has_gstin": row.has_gstin == "Y", "employee_count": int(row.employee_count), "preferred_language": row.preferred_language,
                "contact_name": row.contact_name, "score": round(float(row.score), 3), "reasons": reasons,
                "in_test_split": bool(i in set(self.test_index)),
            })
        return out


@lru_cache(maxsize=1)
def get_model() -> PropensityModel:
    return PropensityModel()
