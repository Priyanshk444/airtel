# Architecture: Project Udyam Digital (Accel Business prototype)

A mobile-first web app with one Python backend. The LLM is used in exactly two places and never decides
anything about products, prices or eligibility.

## Components and data flows

```mermaid
flowchart LR
    subgraph Customer["Shop owner / channel partner (phone browser)"]
        UI["React + Vite SPA<br/>Advisor · Quote · Checkout · KYC · Tracker · Partner"]
    end

    UI -- "/api/* (JSON, multipart)" --> NGINX["nginx<br/>static files + /api proxy"]
    NGINX --> API["FastAPI backend<br/>backend/app/main.py"]

    subgraph Backend["FastAPI backend (one container)"]
        API --> ADV["Advisor service<br/>advisor/service.py"]
        API --> ENG["Rule engine (deterministic)<br/>engine/recommend.py"]
        API --> QUO["Quote & orders<br/>quote.py · orders.py"]
        API --> KYC["Smart KYC<br/>kyc/checks.py · kyc/service.py"]
        API --> PROP["Propensity model<br/>propensity.py (logistic regression)"]
        ADV -- "tool calls:<br/>update_profile · get_recommendation · create_handoff_lead" --> ENG
        ADV -- "guided mode (no LLM)" --> ENG
        QUO --> ENG
        KYC --> REG["Mock GSTIN / Udyam lookup<br/>kyc/registry.py"]
        KYC --> EXT["Vision extraction<br/>kyc/extraction.py"]
    end

    ADV -. "chat turns (claude-haiku-5-5, tools)" .-> CLAUDE[("Anthropic API")]
    EXT -. "document image + JSON schema" .-> CLAUDE

    subgraph Data["data/ (read-only, synthetic)"]
        CAT[("product_catalogue.csv")]
        LEADS[("smb_leads.csv")]
        GST[("mock_gstin_registry.csv")]
        UDY[("mock_udyam_registry.csv")]
        IMG[("kyc_documents/*.png")]
    end
    ENG --> CAT
    PROP --> LEADS
    REG --> GST
    REG --> UDY
    REG -. "contact on record" .-> LEADS
    UI -. "sample documents (demo)" .-> IMG

    DB[("SQLite<br/>sessions · orders · handoff_leads<br/>consents · kyc_cases")]
    ADV --> DB
    QUO --> DB
    KYC --> DB
```

## What each part does

| Part | Responsibility | Deterministic? |
| --- | --- | --- |
| Rule engine (`engine/`) | Eligibility (tier, size, GSTIN, dependencies), bundle per segment, quantities, pricing, reasons | Yes, pure Python, 108 unit tests incl. replay of all 368 real bundles |
| Advisor (`advisor/`) | Talks to the customer in their language and extracts a structured profile through strict tools. Guided (tap) mode does the same without a model. | Model only for language; recommendations always from the engine |
| Quote & orders | Re-prices every line server-side from the catalogue, mock payment, order timeline from install days | Yes |
| Smart KYC (`kyc/`) | Consent record, field extraction, 15 validation checks, masked results, retention | Extraction uses the model; every check is deterministic |
| Propensity (`propensity.py`) | Ranks leads to call, trained on a stratified split, reports held-out metrics and top factors | Yes, seeded |
| Partner views | Handoff leads by territory, lead priority list, assisted mode | Yes |

## Key sequences

### One advisor turn (chat mode)

```mermaid
sequenceDiagram
    participant C as Customer
    participant API as FastAPI
    participant M as Claude Haiku 5.5
    participant E as Rule engine
    C->>API: "Kirana in Nashik, 3 log, GST nahi"
    API->>M: history + strict tools (cached system prompt)
    M-->>API: tool_use update_profile{business_type, city, employee_count, has_gstin}
    API->>API: merge profile, city -> tier 2
    API->>M: tool_result
    M-->>API: tool_use get_recommendation
    API->>E: recommend(profile)
    E-->>API: bundle + exclusions + reasons (names, prices)
    API->>M: tool_result (code-free view)
    M-->>API: reply in Hinglish using only those numbers
    API->>API: sanitise product codes, persist append-only history
    API-->>C: reply + bundle card
```

### One KYC document

```mermaid
sequenceDiagram
    participant C as Customer
    participant API as FastAPI
    participant V as Claude vision
    participant R as Mock registries
    C->>API: consent {verification: true, ...}
    C->>API: upload GST certificate (multipart)
    API->>API: downscale in memory, sha256, bytes never written
    API->>V: image + JSON schema (structured output)
    V-->>API: fields + legibility + confidence
    API->>API: checksum / repair GSTIN
    API->>R: lookup_gstin, lookup_udyam
    R-->>API: status, legal name, address
    API->>API: 15 checks -> pass / fail / review
    API-->>C: masked fields + check list (never the raw IDs)
```

## Runtime

- `docker compose up` starts two containers: `backend` (uvicorn, port 8000) and `frontend` (nginx, port 3000).
- `data/` is mounted read-only into the backend; the SQLite file lives in a named volume.
- `ANTHROPIC_API_KEY` is read from `.env`. Without it the app runs with the guided advisor and the sample KYC documents.
- Models default to `claude-haiku-5-5` (`ADVISOR_MODEL`, `KYC_MODEL` override).

## Code map

```
backend/app/engine/        models.py · catalogue.py · rules.py · recommend.py
backend/app/advisor/       prompts.py · tools.py · service.py
backend/app/kyc/           validators.py · registry.py · checks.py · extraction.py · service.py · specimens.py
backend/app/               quote.py · orders.py · propensity.py · seed.py · db.py · main.py
backend/tests/             160 tests; advisor_scenarios/ (25 live scenarios); fixtures/kyc_golden.json
backend/scripts/           run_kyc_specimens.py
frontend/src/pages/        Home · Advisor · Quote · Checkout · Kyc · Track · Partner
frontend/src/components/   BundleCard · GuidedAdvisor
analysis/explore_data.py   generates docs/data_findings.md
```
