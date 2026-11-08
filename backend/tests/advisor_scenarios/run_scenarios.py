"""
Run the advisor scenarios against the real model and write docs/advisor_test_results.md.

Usage (from backend/):  python -m tests.advisor_scenarios.run_scenarios [--only S03,S07] [--limit N]
Requires ANTHROPIC_API_KEY. Uses a throwaway SQLite file so the demo database is untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import app  # noqa: F401  (loads the project .env before the key check)

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"

# pricing for claude-haiku-5-5 (USD per 1M tokens, prompts <= 100K): input 0.10, output 0.50, cache read 0.01
PRICE_IN, PRICE_OUT, PRICE_CACHE = 0.10, 0.50, 0.01


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated scenario ids")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; cannot run advisor scenarios.", file=sys.stderr)
        return 2

    os.environ["UDYAM_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "scenarios.sqlite")
    from app import db
    from app.advisor import service
    from .scenarios import GLOBAL_CHECKS, SCENARIOS, State

    db.init_db()
    selected = SCENARIOS
    if args.only:
        wanted = {s.strip().upper() for s in args.only.split(",")}
        selected = [s for s in SCENARIOS if s.id in wanted]
    if args.limit:
        selected = selected[: args.limit]

    results = []
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "api_calls": 0}
    for sc in selected:
        print(f"\n=== {sc.id} {sc.title}")
        session = service.create_session()
        replies: list[str] = []
        earlier: list[dict] = []
        error = None
        t0 = time.time()
        try:
            for turn in sc.turns:
                print(f"  USER> {turn}")
                state = service.handle_message(session, turn)
                if session.get("recommendation") and session["recommendation"] not in earlier:
                    earlier.append(session["recommendation"])
                replies.append(state["reply"])
                print(f"  BOT > {state['reply'][:300].replace(chr(10), ' ')}")
        except Exception as exc:  # keep going with other scenarios
            error = f"{type(exc).__name__}: {exc}"
            print("  ERROR", error)
        elapsed = time.time() - t0
        handoff = None
        if session.get("handoff_id"):
            with db.connect() as conn:
                row = conn.execute("SELECT * FROM handoff_leads WHERE id = ?", (session["handoff_id"],)).fetchone()
            handoff = db.row_to_dict(row)
        st = State(replies=replies, profile=session["profile"], recommendation=session.get("recommendation"),
                   stage=session["stage"], handoff=handoff, user_turns=sc.turns,
                   earlier_recommendations=earlier[:-1])
        checks = {}
        for name, fn in {**sc.checks, **GLOBAL_CHECKS}.items():
            try:
                checks[name] = bool(fn(st))
            except Exception as exc:
                checks[name] = False
                print(f"  check {name} raised {exc}")
        usage = session.get("usage") or {}
        for k in totals:
            totals[k] += usage.get(k, 0)
        passed = all(checks.values()) and error is None
        print(f"  -> {'PASS' if passed else 'FAIL'} {checks}")
        results.append({
            "id": sc.id, "title": sc.title, "category": sc.category, "passed": passed, "error": error,
            "checks": checks, "turns": sc.turns, "replies": replies, "profile": session["profile"],
            "items": [(i["product_id"], i["product_name"], i["quantity"], i["monthly_inr"]) for i in (session.get("recommendation") or {}).get("items", [])],
            "excluded": [(e["product_id"], e["reasons"][0]["code"]) for e in (session.get("recommendation") or {}).get("excluded", [])],
            "pricing": (session.get("recommendation") or {}).get("pricing"), "stage": session["stage"],
            "handoff": {"reason": handoff["reason"], "summary": handoff["summary"]} if handoff else None,
            "usage": usage, "seconds": round(elapsed, 1),
        })

    cost = (totals["input_tokens"] * PRICE_IN + totals["output_tokens"] * PRICE_OUT + totals["cache_read_input_tokens"] * PRICE_CACHE) / 1e6
    write_report(results, totals, cost)
    (DOCS / "advisor_test_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    n_pass = sum(r["passed"] for r in results)
    print(f"\n{n_pass}/{len(results)} scenarios passed. Tokens: {totals}. Estimated cost: ${cost:.2f}")
    return 0 if n_pass == len(results) else 1


def write_report(results: list[dict], totals: dict, cost: float) -> None:
    n_pass = sum(r["passed"] for r in results)
    n_checks = sum(len(r["checks"]) for r in results)
    n_checks_pass = sum(sum(r["checks"].values()) for r in results)
    lines = [
        "# Advisor scenario test results", "",
        f"Model: `{service_model()}` · {len(results)} scenarios · **{n_pass} passed, {len(results) - n_pass} failed** · "
        f"{n_checks_pass}/{n_checks} individual checks passed.", "",
        f"Token usage for the whole run: {totals['input_tokens']:,} input (of which {totals['cache_read_input_tokens']:,} served from cache), "
        f"{totals['output_tokens']:,} output, {totals['api_calls']} API calls. Estimated cost: **${cost:.2f}**.", "",
        "Every scenario also ran two global checks: no product codes in any reply, and no rupee amount in a reply that is not in the rule-engine output.", "",
        "| # | Scenario | Category | Result | Failed checks |", "|---|---|---|---|---|",
    ]
    for r in results:
        failed = [k for k, v in r["checks"].items() if not v]
        lines.append(f"| {r['id']} | {r['title']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | {', '.join(failed) or ('error: ' + r['error'] if r['error'] else '-')} |")
    lines += ["", "## Transcripts", ""]
    for r in results:
        lines += [f"### {r['id']} - {r['title']} ({'PASS' if r['passed'] else 'FAIL'})", ""]
        for turn, reply in zip(r["turns"], r["replies"] + [""] * (len(r["turns"]) - len(r["replies"]))):
            lines += [f"**Customer:** {turn}", "", f"**Advisor:** {reply.replace(chr(10), '  ' + chr(10))}", ""]
        if r["items"]:
            lines.append("Engine bundle: " + "; ".join(f"{n} x{q} (Rs {m:,})" for _, n, q, m in r["items"]) +
                         f" - total Rs {r['pricing']['monthly_total_inr']:,}/month, setup Rs {r['pricing']['setup_total_inr']:,}, {r['pricing']['contract_months']} months.")
        if r["excluded"]:
            lines.append("Excluded: " + ", ".join(f"{p} ({c})" for p, c in r["excluded"]))
        if r["handoff"]:
            lines.append(f"Handoff ({r['handoff']['reason']}): {r['handoff']['summary']}")
        lines.append(f"Checks: " + ", ".join(f"{k}={'ok' if v else 'FAIL'}" for k, v in r["checks"].items()))
        lines.append("")
    (DOCS / "advisor_test_results.md").write_text("\n".join(lines), encoding="utf-8")


def service_model() -> str:
    from app.advisor import service
    return service.MODEL


if __name__ == "__main__":
    sys.exit(main())
