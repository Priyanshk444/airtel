# Project Udyam Digital: Accel Business prototype

Digital-first acquisition and onboarding journey for small businesses: a multilingual advisor, one-price quote,
mock checkout, DPDP-compliant Smart KYC, order tracker, and a partner back office. Built for the YTL Hackathon
2026 (Enterprise Track A) around a fictional operator, **Accel Telecom / Accel Business**. All data is synthetic.

## Run it (Windows + Docker Desktop)

1. Install and start Docker Desktop. Wait until it shows "Engine running".
2. Optional: copy `.env.example` to `.env` and put your Anthropic API key in it. Without a key the app still runs
   with the tap-to-answer advisor and the 12 sample KYC documents; free-text chat and reading new photos need it.
3. In PowerShell:

```
cd <this folder>
docker compose up --build
```

4. Open http://localhost:3000 (API docs at http://localhost:8000/docs). First build takes a few minutes.
5. Stop with Ctrl+C. `docker compose down -v` also wipes the demo database.

### Without Docker

```
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd backend && ..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# second window
cd frontend && npm install && npm run dev
```

## What is in the box

| Step | Where | Notes |
| --- | --- | --- |
| Advisor | `/advisor` | Chat (Hindi / English / Hinglish) with Claude tools, or tap-to-answer; both use the same rule engine |
| Quote and checkout | `/quote`, `/checkout` | Server-side repricing, add-on toggles, mock payment (type `FAIL` to see a decline) |
| Smart KYC | `/kyc` | Consent screen, vision extraction, 15 checks, mock GSTIN/Udyam lookups, masking, retention |
| Tracker | `/track` | Timeline with expected dates, demo "simulate next step" |
| Partner | `/partner` | Handoff leads by territory, propensity-ranked call list, assisted mode |

Demo businesses and orders are seeded on first start (`backend/app/seed.py`).

## Tests and scripts

```
cd backend
..\.venv\Scripts\python -m pytest                                   # 160 tests, no API key needed
..\.venv\Scripts\python -m scripts.run_kyc_specimens --fixture       # 12 applicants -> docs/kyc_results.md
..\.venv\Scripts\python -m scripts.run_kyc_specimens                 # same, with real vision extraction (key)
..\.venv\Scripts\python -m tests.advisor_scenarios.run_scenarios     # 25 live advisor scenarios (key)
..\.venv\Scripts\python ..\analysis\explore_data.py                  # regenerates docs/data_findings.md
```

## Documents

- `docs/data_findings.md`: funnel, segments, planted signals, unit economics (generated from the data)
- `docs/architecture.md`: components, data flows (Mermaid)
- `docs/privacy_note.md`: DPDP choices actually implemented
- `docs/business_case_outline.md`: 10-slide outline with baselines from the data
- `docs/demo_script.md`: 3-minute demo
- `demo/udyam_digital_demo.mp4`: 2:37 walkthrough of the whole journey, captions read aloud (brief limit: 3 minutes). Re-record with `.venv\Scripts\python demo
ecord_demo.py` while the app is running (needs `pip install playwright imageio-ffmpeg` and `python -m playwright install ffmpeg`).
- `docs/kyc_results.md`: what was flagged for each of the 12 applicants (live vision run, 47 reads, about $0.02)
- `docs/advisor_test_results.md`: transcripts and checks for the 25 live advisor scenarios (about $0.03 per run)

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | unset | Enables chat advisor and vision extraction |
| `ADVISOR_MODEL` | `claude-haiku-5-5` | Chat model |
| `KYC_MODEL` | `claude-haiku-5-5` | Document reader |
| `KYC_TODAY` | `2026-07-15` | "Today" for date checks, per the data README |
| `UDYAM_DATA_DIR` | `data/` | Location of the CSV pack |
| `UDYAM_DB_PATH` | `backend/var/app.sqlite` | SQLite file |
