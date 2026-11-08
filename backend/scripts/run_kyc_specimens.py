"""
Run all 12 KYC applicants through the pipeline and write docs/kyc_results.md.

  python -m scripts.run_kyc_specimens            # Claude vision extraction (needs ANTHROPIC_API_KEY)
  python -m scripts.run_kyc_specimens --fixture  # hand-read golden fields, no API

With the API, the extracted fields are also diffed against the golden fixture so we can see how
well the vision step reads each document.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "backend"))

from app.kyc import checks as C, specimens  # noqa: E402
from app.kyc.extraction import extract_fields  # noqa: E402

FIELDS_TO_COMPARE = {
    "gst_certificate": ["gstin", "legal_name", "trade_name", "constitution", "address", "date_of_liability"],
    "udyam_certificate": ["udyam_number", "enterprise_name", "city", "state", "date_of_registration"],
    "signatory_id": ["name", "designation", "business_name", "id_number", "valid_till"],
    "address_proof": ["billed_to", "supply_address", "bill_date", "consumer_number"],
}
PRICE_IN, PRICE_OUT = 0.10, 0.50   # USD per 1M tokens, claude-haiku-5-5 (prompts <= 100K tokens)


def norm(v):
    return " ".join(str(v or "").split()).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true", help="use hand-read fields instead of calling the vision API")
    ap.add_argument("--only", help="comma-separated applicants, e.g. K01,K07")
    args = ap.parse_args()
    use_api = not args.fixture
    if use_api and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set; re-run with --fixture or set the key.", file=sys.stderr)
        return 2

    golden = specimens.golden()
    wanted = sorted(golden) if not args.only else [a.strip().upper() for a in args.only.split(",")]
    rows, usage = [], {"input": 0, "output": 0, "calls": 0}
    extraction_diffs = []
    for applicant in wanted:
        docs = {}
        t0 = time.time()
        for doc_type in specimens.DOC_TYPES:
            path = specimens.specimen_path(applicant, doc_type)
            if not path:
                continue
            if use_api:
                fields = extract_fields(doc_type, path.read_bytes())
                usage["input"] += fields["_meta"]["input_tokens"]; usage["output"] += fields["_meta"]["output_tokens"]; usage["calls"] += 1
                gold = golden[applicant].get(doc_type, {})
                for f in FIELDS_TO_COMPARE[doc_type]:
                    if norm(fields.get(f)) != norm(gold.get(f)):
                        extraction_diffs.append((applicant, doc_type, f, gold.get(f), fields.get(f)))
            else:
                fields = golden[applicant][doc_type]
            docs[doc_type] = fields
        result = C.run_checks(docs, "gstin")
        flagged = [c for c in result["checks"] if c["status"] in ("fail", "review")]
        rows.append({"applicant": applicant, "business": docs.get("gst_certificate", {}).get("trade_name"), "overall": result["overall"],
                     "flags": [(c["code"], c["status"], c["reason"]) for c in flagged], "summary": result["summary"],
                     "checks": result["checks"], "seconds": round(time.time() - t0, 1)})
        print(f"{applicant} {result['overall']:13s} " + "; ".join(f"{c}={s}" for c, s, _ in rows[-1]["flags"]))

    write_report(rows, use_api, usage, extraction_diffs)
    (DOCS / "kyc_results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def write_report(rows, use_api, usage, diffs):
    mode = "Claude vision extraction (`claude-haiku-5-5`, structured output)" if use_api else "hand-read golden fields (no API call)"
    lines = [
        "# Smart KYC - results for the 12 specimen applicants", "",
        f"Extraction mode: {mode}. Validation date fixed at 2026-07-15 (README). Identifiers are masked in all output.", "",
    ]
    if use_api:
        cost = (usage["input"] * PRICE_IN + usage["output"] * PRICE_OUT) / 1e6
        lines += [f"Vision calls: {usage['calls']} · {usage['input']:,} input tokens · {usage['output']:,} output tokens · estimated cost ${cost:.2f}.", ""]
    lines += ["| Applicant | Business | Decision | What was flagged |", "|---|---|---|---|"]
    for r in rows:
        flags = "<br>".join(f"**{s.upper()}** {c}: {reason}" for c, s, reason in r["flags"]) or "all checks passed"
        lines.append(f"| {r['applicant']} | {r['business'] or '-'} | {r['overall']} | {flags} |")
    counts = {k: sum(1 for r in rows if r["overall"] == k) for k in ("verified", "needs_review", "failed")}
    lines += ["", f"Totals: {counts['verified']} verified, {counts['needs_review']} need review, {counts['failed']} failed.", ""]
    if use_api:
        lines += ["## Extraction accuracy against the hand-read fixture", ""]
        if diffs:
            lines += ["| Applicant | Document | Field | Hand-read | Claude read |", "|---|---|---|---|---|"]
            lines += [f"| {a} | {d} | {f} | {g} | {v} |" for a, d, f, g, v in diffs]
        else:
            lines.append("Every compared field matched the hand-read fixture exactly.")
        lines.append("")
    lines += ["## Full check list per applicant", ""]
    for r in rows:
        lines += [f"### {r['applicant']} - {r['business'] or ''} ({r['overall']})", "", r["summary"], "", "| Check | Status | Reason |", "|---|---|---|"]
        lines += [f"| {c['title']} | {c['status']} | {c['reason']} |" for c in r["checks"]]
        lines.append("")
    (DOCS / "kyc_results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {DOCS / 'kyc_results.md'}")


if __name__ == "__main__":
    sys.exit(main())
