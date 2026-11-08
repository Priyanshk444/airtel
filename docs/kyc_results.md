# Smart KYC - results for the 12 specimen applicants

Extraction mode: Claude vision extraction (`claude-haiku-5-5`, structured output). Validation date fixed at 2026-07-15 (README). Identifiers are masked in all output.

Vision calls: 47 · 134,878 input tokens · 13,161 output tokens · estimated cost $0.02.

| Applicant | Business | Decision | What was flagged |
|---|---|---|---|
| K01 | Vindhya Tours & Travels | failed | **FAIL** gstin_status: GST registration is cancelled in the registry. GST-only products cannot be sold; the customer can continue with Udyam or other documents for the rest of the bundle.<br>**FAIL** udyam_format: The Udyam certificate has no registration number printed on it. |
| K02 | Harmony Dental Care | needs_review | **REVIEW** quality_gst_certificate: The GST certificate is skewed (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up.<br>**REVIEW** gstin_format: GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 19**********1ZL passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| K03 | Ganesh Woodcraft | verified | all checks passed |
| K04 | Saffron Dental Care LLP | needs_review | **REVIEW** quality_gst_certificate: The GST certificate is blurred (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up.<br>**REVIEW** gstin_format: GSTIN as printed fails the format check (position 12: 0 -> O; position 14: 2 -> Z). It looks like a letter/digit mix-up; 27**********1ZH passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| K05 | Balaji Realty LLP | verified | all checks passed |
| K06 | Saffron Unisex Salon | failed | **FAIL** gstin_format: GSTIN 08**********1Z0 is not a valid GSTIN (structure or checksum is wrong). Ask for a clear photo of the certificate. |
| K07 | Neelgiri Physio Clinic | failed | **FAIL** pan_consistency: PAN name letter 'N' does not match: Shri Physio Clinic.<br>**FAIL** name_consistency: The legal name says the business is 'shri physio clinic' but the trade name is 'neelgiri physio clinic'. |
| K08 | Green Leaf Legal Associates | needs_review | **REVIEW** gstin_format: GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 24**********1Z3 passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| K09 | Kaveri Insurance Advisors | verified | all checks passed |
| K10 | Kaveri Stays LLP | needs_review | **REVIEW** signatory_authority: Nisha Arora signs as 'owner' for a limited liability partnership, but 'owner' is not a signing role for this entity type and the person is not the contact on record. A partner/board resolution naming the signatory is needed. |
| K11 | Trinity Bake House Pvt Ltd | failed | **FAIL** address_proof_recent: The bill is 257 days old; address proof must be no older than 90 days. Please upload a recent bill. |
| K12 | Star Electronics | verified | all checks passed |

Totals: 4 verified, 4 need review, 4 failed.

## Extraction accuracy against the hand-read fixture

| Applicant | Document | Field | Hand-read | Claude read |
|---|---|---|---|---|
| K03 | gst_certificate | address | Shop/Unit 80, Civil Lines, Nagpur, Maharashtra - 411231 | Shop/Unit 80, Civil Lines, Nagpur, Maharashtra a - 411231 |
| K04 | gst_certificate | gstin | 27PZSXS1936D1ZH | 27PZSXS1936012H |

## Full check list per applicant

### K01 - Vindhya Tours & Travels (failed)

We could not verify the business yet: GST registration is cancelled in the registry. GST-only products cannot be sold; the customer can continue with Udyam or other documents for the rest of the bundle.; The Udyam certificate has no registration number printed on it.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 37**********1ZS has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 37**********1ZS is registered to Neha Kaur (Prop. Vindhya Tours & Travels) in Andhra Pradesh. |
| GSTIN status | fail | GST registration is cancelled in the registry. GST-only products cannot be sold; the customer can continue with Udyam or other documents for the rest of the bundle. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 37 = Andhra Pradesh, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********7L embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | fail | The Udyam certificate has no registration number printed on it. |
| Business name is consistent across documents | pass | 'Vindhya Tours & Travels' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****90 is valid until 2028-03-26. |
| Signatory is authorised for this business | pass | Neha Kaur is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 19 days old (limit 90). |

### K02 - Harmony Dental Care (needs_review)

A few things need a quick look by our team: The GST certificate is skewed (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up.; GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 19**********1ZL passes the checksum and was used for the registry lookup. Please confirm with the customer.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| Image quality: GST certificate | review | The GST certificate is skewed (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up. |
| GSTIN format and checksum | review | GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 19**********1ZL passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| GSTIN found in GST registry | pass | GSTIN 19**********1ZL is registered to Joseph Shah (Prop. Harmony Dental Care) in West Bengal. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 19 = West Bengal, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********5Y embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-WB-00-*****30 is well-formed and its state code WB matches West Bengal. |
| Udyam number found in registry | pass | Registered to Harmony Dental Care (Small, Services) in Kolkata. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Harmony Dental Care' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****07 is valid until 2028-09-10. |
| Signatory is authorised for this business | pass | Joseph Shah is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 54 days old (limit 90). |

### K03 - Ganesh Woodcraft (verified)

All checks passed. Your business is verified and the order can move to installation.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 27**********1ZP has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 27**********1ZP is registered to Joseph Singh (Prop. Ganesh Woodcraft) in Maharashtra. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 27 = Maharashtra, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********7D embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-MH-00-*****96 is well-formed and its state code MH matches Maharashtra. |
| Udyam number found in registry | pass | Registered to Ganesh Woodcraft (Micro, Manufacturing) in Nagpur. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Ganesh Woodcraft' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****89 is valid until 2028-07-04. |
| Signatory is authorised for this business | pass | Joseph Singh is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 46 days old (limit 90). |

### K04 - Saffron Dental Care LLP (needs_review)

A few things need a quick look by our team: The GST certificate is blurred (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up.; GSTIN as printed fails the format check (position 12: 0 -> O; position 14: 2 -> Z). It looks like a letter/digit mix-up; 27**********1ZH passes the checksum and was used for the registry lookup. Please confirm with the customer.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| Image quality: GST certificate | review | The GST certificate is blurred (reader confidence 50%). Values read from it will be double-checked by our team; a clearer photo speeds this up. |
| GSTIN format and checksum | review | GSTIN as printed fails the format check (position 12: 0 -> O; position 14: 2 -> Z). It looks like a letter/digit mix-up; 27**********1ZH passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| GSTIN found in GST registry | pass | GSTIN 27**********1ZH is registered to Saffron Dental Care LLP in Maharashtra. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 27 = Maharashtra, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********6O embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-MH-00-*****36 is well-formed and its state code MH matches Maharashtra. |
| Udyam number found in registry | pass | Registered to Saffron Dental Care LLP (Micro, Services) in Nagpur. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Saffron Dental Care LLP' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****96 is valid until 2028-08-03. |
| Signatory is authorised for this business | pass | Fatima Pillai signs as 'partner' for a limited liability partnership and matches the contact on record. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 48 days old (limit 90). |

### K05 - Balaji Realty LLP (verified)

All checks passed. Your business is verified and the order can move to installation.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. Not provided (optional for this path): Udyam certificate. |
| GSTIN format and checksum | pass | GSTIN 32**********1Z1 has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 32**********1Z1 is registered to Balaji Realty LLP in Kerala. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 32 = Kerala, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********1U embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | not_applicable | No Udyam certificate provided; not required on the GSTIN path. |
| Business name is consistent across documents | pass | 'Balaji Realty LLP' appears consistently on all 3 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****34 is valid until 2029-09-11. |
| Signatory is authorised for this business | pass | Anita Shah signs as 'owner' for a limited liability partnership and matches the contact on record. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 34 days old (limit 90). |

### K06 - Saffron Unisex Salon (failed)

We could not verify the business yet: GSTIN 08**********1Z0 is not a valid GSTIN (structure or checksum is wrong). Ask for a clear photo of the certificate.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | fail | GSTIN 08**********1Z0 is not a valid GSTIN (structure or checksum is wrong). Ask for a clear photo of the certificate. |
| GSTIN found in GST registry | not_applicable | Skipped because no valid GSTIN was available. |
| PAN inside the GSTIN matches the other documents | not_applicable | Skipped: no valid GSTIN. |
| Udyam registration number | pass | UDYAM-RJ-00-*****57 is well-formed and its state code RJ matches Rajasthan. |
| Udyam number found in registry | pass | Registered to Saffron Unisex Salon (Micro, Trading) in Jaipur. |
| Business name is consistent across documents | pass | 'Saffron Unisex Salon' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****54 is valid until 2028-09-15. |
| Signatory is authorised for this business | pass | Pooja Shah is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 34 days old (limit 90). |

### K07 - Neelgiri Physio Clinic (failed)

We could not verify the business yet: PAN name letter 'N' does not match: Shri Physio Clinic.; The legal name says the business is 'shri physio clinic' but the trade name is 'neelgiri physio clinic'.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 07**********1ZT has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 07**********1ZT is registered to Neha Banerjee (Prop. Neelgiri Physio Clinic) in Delhi. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 07 = Delhi, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | fail | PAN name letter 'N' does not match: Shri Physio Clinic. |
| Udyam registration number | pass | UDYAM-DL-00-*****47 is well-formed and its state code DL matches Delhi. |
| Udyam number found in registry | pass | Registered to Neelgiri Physio Clinic (Small, Services) in Delhi. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | fail | The legal name says the business is 'shri physio clinic' but the trade name is 'neelgiri physio clinic'. |
| Signatory ID is valid | pass | ID SYN-ID-****37 is valid until 2030-05-05. |
| Signatory is authorised for this business | pass | Neha Banerjee is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 10 days old (limit 90). |

### K08 - Green Leaf Legal Associates (needs_review)

A few things need a quick look by our team: GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 24**********1Z3 passes the checksum and was used for the registry lookup. Please confirm with the customer.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | review | GSTIN as printed fails the format check (position 4: 0 -> O). It looks like a letter/digit mix-up; 24**********1Z3 passes the checksum and was used for the registry lookup. Please confirm with the customer. |
| GSTIN found in GST registry | pass | GSTIN 24**********1Z3 is registered to Joseph Rao (Prop. Green Leaf Legal Associates) in Gujarat. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 24 = Gujarat, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********5M embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-GJ-00-*****45 is well-formed and its state code GJ matches Gujarat. |
| Udyam number found in registry | pass | Registered to Green Leaf Legal Associates (Small, Services) in Vadodara. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Green Leaf Legal Associates' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****48 is valid until 2027-09-18. |
| Signatory is authorised for this business | pass | Joseph Rao is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 50 days old (limit 90). |

### K09 - Kaveri Insurance Advisors (verified)

All checks passed. Your business is verified and the order can move to installation.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 37**********1ZB has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 37**********1ZB is registered to Anita Kulkarni (Prop. Kaveri Insurance Advisors) in Andhra Pradesh. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 37 = Andhra Pradesh, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********6F embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-AP-00-*****62 is well-formed and its state code AP matches Andhra Pradesh. |
| Udyam number found in registry | pass | Registered to Kaveri Insurance Advisors (Micro, Services) in Visakhapatnam. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Kaveri Insurance Advisors' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****40 is valid until 2027-12-22. |
| Signatory is authorised for this business | pass | Anita Kulkarni is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 5 days old (limit 90). |

### K10 - Kaveri Stays LLP (needs_review)

A few things need a quick look by our team: Nisha Arora signs as 'owner' for a limited liability partnership, but 'owner' is not a signing role for this entity type and the person is not the contact on record. A partner/board resolution naming the signatory is needed.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 27**********1ZL has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 27**********1ZL is registered to Kaveri Stays LLP in Maharashtra. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 27 = Maharashtra, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********8U embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-MH-00-*****41 is well-formed and its state code MH matches Maharashtra. |
| Udyam number found in registry | pass | Registered to Kaveri Stays LLP (Small, Trading) in Mumbai. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Kaveri Stays LLP' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****42 is valid until 2029-06-01. |
| Signatory is authorised for this business | review | Nisha Arora signs as 'owner' for a limited liability partnership, but 'owner' is not a signing role for this entity type and the person is not the contact on record. A partner/board resolution naming the signatory is needed. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 27 days old (limit 90). |

### K11 - Trinity Bake House Pvt Ltd (failed)

We could not verify the business yet: The bill is 257 days old; address proof must be no older than 90 days. Please upload a recent bill.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 03**********1ZZ has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 03**********1ZZ is registered to Trinity Bake House Pvt Ltd in Punjab. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 03 = Punjab, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********0R embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-PB-00-*****78 is well-formed and its state code PB matches Punjab. |
| Udyam number found in registry | pass | Registered to Trinity Bake House Pvt Ltd (Micro, Trading) in Ludhiana. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Trinity Bake House Pvt Ltd' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****12 is valid until 2028-12-23. |
| Signatory is authorised for this business | pass | Vikram Pillai signs as 'owner' for a private limited company and matches the contact on record. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | fail | The bill is 257 days old; address proof must be no older than 90 days. Please upload a recent bill. |

### K12 - Star Electronics (verified)

All checks passed. Your business is verified and the order can move to installation.

| Check | Status | Reason |
|---|---|---|
| Required documents uploaded | pass | All documents required for the gstin path are present. |
| GSTIN format and checksum | pass | GSTIN 37**********1ZU has the correct 15-character structure and checksum. |
| GSTIN found in GST registry | pass | GSTIN 37**********1ZU is registered to Pooja Agarwal (Prop. Star Electronics) in Andhra Pradesh. |
| GSTIN status | pass | GST registration is active. |
| Certificate details match the registry | pass | Legal name, trade name and address on the certificate match the registry record. |
| Registration date matches the registry | pass | Date of liability on the certificate matches the registry. |
| GSTIN state code matches the address | pass | State code 37 = Andhra Pradesh, which matches the address on the certificate. |
| PAN inside the GSTIN matches the other documents | pass | PAN ********5E embedded in the GSTIN is consistent with the business name on every document. |
| Udyam registration number | pass | UDYAM-AP-00-*****72 is well-formed and its state code AP matches Andhra Pradesh. |
| Udyam number found in registry | pass | Registered to Star Electronics (Micro, Trading) in Visakhapatnam. |
| Udyam and GSTIN describe the same business | pass | Udyam and GST records agree on name, state and city. |
| Business name is consistent across documents | pass | 'Star Electronics' appears consistently on all 4 documents. |
| Signatory ID is valid | pass | ID SYN-ID-****12 is valid until 2029-03-03. |
| Signatory is authorised for this business | pass | Pooja Agarwal is the proprietor named on the GST certificate. |
| Address proof matches the registered address | pass | The utility bill is for the same address as the GST registration. |
| Address proof is recent | pass | The bill is 9 days old (limit 90). |
