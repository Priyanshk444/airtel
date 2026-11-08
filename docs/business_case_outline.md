# Business case outline (10 slides)

All figures are computed from the synthetic pack by `analysis/explore_data.py` (see `docs/data_findings.md`).
Targets are **assumptions** and are labelled as such.

## Slide 1: The problem in one number

- 5,000 leads in a quarter, 368 activations: **7.4%**. Average 17.6 days to activate, 3 status-chasing calls,
  blended acquisition cost **Rs 15,053** per activated customer.
- **59% of all drops are our own process failures** (unreachable, visit never happened, quote too slow or too
  complex, paperwork, installation delay), not customers saying no.
- NPS of activated customers is **-25**.

## Slide 2: What the data says is broken

- Quote stage loses 1,113 leads; 385 of them because the quote was *too complex* or *too slow*.
- Status chasing destroys loyalty: 1 call -> NPS 7.5, churn 6%; 5 calls -> NPS 6.0, churn 28%.
- Sales ignores the ask: only 28% of the products a lead asked about end up in the bundle; 719 asked about
  5G AirFiber, 9 got it, 41 were dropped as "site not feasible for fibre".
- 48 of 368 sold bundles break a catalogue rule; 22 activations have a cancelled or suspended GSTIN.
- Udyam-only businesses pass KYC at 29% vs 81% for GSTIN holders: a dead end for half of micro leads.

## Slide 3: Target customer, in order

1. **Professional offices** (clinics, CA firms, coaching centres): 138 activations, 11.1% conversion, lowest
   CAC (Rs 10,695), 1.6-month revenue payback on a Rs 6,796 bundle, 86% have a GSTIN. Uniform needs, no site survey.
2. **Small multi-site** (chains, 3-10 outlets): Rs 31,233/month average, 57% of all recurring value from 23% of
   activations. Advisor quotes, partner installs.
3. **Micro retail** only through self-serve: 54% of leads, 4.1% conversion, CAC Rs 20,007 against a Rs 2,505
   bundle. The field model cannot serve them; digital sources already acquire at Rs 4,000-6,400.
4. **Manufacturers** stay field-assisted (leased lines, 20.5-day installs, NPS -46), with the advisor for discovery.

## Slide 4: The product

- One chat (Hindi / English / Hinglish, or tap-to-answer) -> one monthly price -> consent -> instant KYC -> tracker.
- The model only talks; a rule engine decides. Every exclusion is explained and the nearest eligible
  alternative is offered. Shown live on the 15 judge scenarios.

## Slide 5: Pricing and savings

- Prices are the catalogue list prices; the bundle logic reproduces the pricing of all 368 historical bundles
  exactly (setup = sum of fees, contract = longest minimum term).
- Savings per lead: field sales spends a fixed Rs 2,690 on every needs visit and Rs 4,030 per activation;
  partners earn 1.5-2.2x the monthly bundle on activation. Field + partner = 85% of acquisition spend.
- **Assumption:** digital discovery replaces the visit for professional offices and micro; the partner is kept
  for installation and multi-site, so the partner commission stays.

## Slide 6: Rollout

- **Quarter 1:** tier-1 cities (Delhi, Mumbai, Pune, Bengaluru), professional offices, inbound and website leads
  first (they are contacted only 55% of the time today yet buy the biggest bundles).
- **Quarter 2:** multi-site with partner-assisted install; micro via WhatsApp-campaign leads on the self-serve path.
- **Quarter 3:** tier-2 cities (installs run 1.5 days slower; tracker expectations set accordingly).

## Slide 7: Field force and partners

- Field force moves from micro visits to site surveys for multi-site and manufacturers, and to the review queue
  for KYC "needs review" cases.
- Partners get three things from the app: handoff leads with the full conversation summary by territory, a
  ranked call list (propensity model), and assisted mode to fill the journey on a shop owner's phone.
- Commission stays activation-based, so the digital journey adds leads to partners instead of competing.

## Slide 8: Success metrics (baseline from data, targets are assumptions)

| Metric | Baseline (Apr-Jun 2026) | Target after 2 quarters |
| --- | --- | --- |
| Lead-to-activation | 7.4% | 12% (professional offices already at 11.1%; digital leads contacted >90%) |
| Time to activate | 17.6 days | 7 days (same-day KYC; install days are the floor: 5 for fibre) |
| Acquisition cost per activation | Rs 15,053 | Rs 8,000 (digital sources already at Rs 4,000-6,400) |
| Status-chasing calls per customer | 3.0 | under 1 |
| 6-month churn | 15.2% (56 of 368) | 10% (customers with 1 call churn at 6%) |

## Slide 9: Risks and mitigations

- **Model cost or outage** -> rule engine is deterministic; tap-to-answer mode runs with no model; Haiku-class
  model keeps a chat under a rupee.
- **KYC false passes or fails** -> registry status, checksum and cross-document checks are code; anything
  uncertain goes to a human review queue, never silently through.
- **Fibre not feasible** -> AirFiber offered automatically; flagged in the profile.
- **DPDP compliance** -> consent before upload, no image storage, masking, retention date; gaps listed in the
  privacy note.
- **Partner resistance** -> partners keep activation commission and gain leads; measured by handoff close rate.

## Slide 10: Ask

- Pilot in 4 tier-1 cities for one quarter with 20 partners; success = 12% conversion on professional offices
  and under 1 follow-up call per order.
