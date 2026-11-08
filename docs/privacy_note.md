# Privacy and security note (1 page)

What the prototype actually implements, mapped to the Digital Personal Data Protection Act, 2023. Where the
prototype stops short of production, it says so.

## Consent (DPDP s.6)

- A consent screen appears **before any document can be uploaded**. The KYC API refuses to open a case without a
  recorded verification consent (`403`).
- Four purposes are presented separately, each with *what we collect, why, and how long we keep it*:
  verification (required), service updates on WhatsApp/SMS, offers, and sharing with a local partner for
  installation. The optional ones are unticked by default.
- Every consent is stored with a timestamp and the notice version (`consents` table), so a change to the notice
  needs fresh consent.

## Purpose limitation

- Each step collects only what that step needs. The advisor profile holds business facts (type, city, size, GST
  status, needs); it never asks for Aadhaar, PAN, bank details or OTPs, and the system prompt forbids it.
- KYC on the GSTIN path needs three documents; the Udyam-only path needs three; the alternative path needs two.
  Documents not required for a path are optional and never demanded.
- The CRM record (`smb_leads.csv`) is used in KYC for one thing only: to corroborate that the signatory is the
  contact on record.

## Data minimisation

- **Images are never stored.** An uploaded image is downscaled in memory, hashed, sent to the reader, and
  discarded. Only the extracted fields and the check results are kept.
- The reader receives the image and a fixed JSON schema, nothing else about the customer.
- Order, quote and handoff records store the profile, not the conversation's model history, except the
  advisor session itself, which keeps its transcript to serve the chat.

## Retention and erasure

- Each KYC case carries a `retention_until` date (90 days). `purge_expired()` blanks the extracted fields and
  keeps only the decision, so the audit trail survives without the personal data.
- Stated retention per purpose is shown to the customer on the consent screen.

## Masking in the UI and logs

- GSTIN, Udyam number, ID number and consumer number are masked in every API response (`37**********1ZS`,
  `UDYAM-MH-00-*****96`) and inside every check reason. A test asserts no unmasked identifier appears in output.
- Logs record case IDs, document types, legibility and confidence, never field values.
- The advisor sanitiser removes product codes; the KYC masking removes identifiers; the handoff summary is written
  from the profile, not from raw documents.

## Access control and security

- Secrets come only from environment variables (`.env`, git-ignored); no key is in code or the frontend.
- The frontend never calls the model; all model calls go through the backend, which owns the key.
- `data/` is mounted read-only in the container; the database is in a private volume.
- **Not implemented (prototype):** partner login and territory-scoped access on the dashboard, audit logging of
  who viewed a KYC case, encryption at rest for SQLite, and a customer-facing "withdraw consent / delete my
  data" button. In production these would sit on the existing `consents` and `kyc_cases` tables; the data model
  already keeps the per-purpose consent needed to honour withdrawal.

## Model usage

- Two uses only: conversation (profile extraction through tools) and document field extraction. Prices,
  eligibility and KYC decisions are deterministic code, so a model error cannot invent a product, a price or a
  pass.
- Prompts contain no personal data beyond the customer's own messages and the document image being read.
