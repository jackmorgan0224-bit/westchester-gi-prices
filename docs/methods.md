# Methods and data notes

## Procedures

| Family | Codes analyzed (core) | Also extracted |
|---|---|---|
| Colonoscopy | 45378 diagnostic · 45380 with biopsy · 45385 snare polyp removal · G0121 screening, average risk · G0105 screening, high risk | 45381, 45384, 45388, 45390 |
| Upper endoscopy (EGD) | 43235 diagnostic · 43239 with biopsy | 43248, 43249, 43251, 43255 |
| Endoscopic ultrasound (EUS) | 43259 upper EUS · 43237 limited · 43238 limited with FNA · 43242 transmural FNA | 45391, 45392 |

Code list and plain-English labels: [`data/reference/gi_codes.csv`](../data/reference/gi_codes.csv).

## Hospitals

The 10 general acute care hospitals in Westchester County listed in CMS Care Compare. Blythedale Children's (pediatric rehab) and Four Winds (psychiatric) are excluded. NYP Westchester bills under NewYork-Presbyterian's main license and appears in NYP's system-wide file.

## Extraction

Files were found through each hospital's `cms-hpt.txt` index ([`src/fetch_mrfs.py`](../src/fetch_mrfs.py)). [`src/extract_gi.py`](../src/extract_gi.py) keeps any row where one of the code columns holds a target CPT/HCPCS code. Values are copied as published. Nothing is filled in or estimated.

- **CSV tall** (Montefiore hospitals, White Plains, St. John's, St. Joseph's): filtered in DuckDB, one output row per input row.
- **CSV wide** (Westchester Medical Center): each row is unpivoted into one row per payer/plan column group that carries a rate.
- **JSON** (NYP, Northwell): streamed with `ijson`. Northwell's files start with a byte order mark, which the extractor strips.

## Which rows count as "the price"

For price comparisons ([`sql/01_build.sql`](../sql/01_build.sql)):

1. **Outpatient facility rows with no modifier.** Inpatient rows and professional (physician) rows are excluded, because the Medicare benchmark is the outpatient facility payment.
2. **Published dollar amounts only.** Percentage and algorithm rates are counted in [`results/coverage.csv`](../results/coverage.csv) but not converted.
3. **Case rate first.** Several hospitals publish two kinds of rows for the same plan and code: a case rate (one price for the visit) and a fee-schedule line (one line of the bill, such as the procedure room). Medicare's OPPS payment is also one bundled payment per visit, so the case rate is the comparable number. When a plan has both, the case rate is used; fee-schedule rows are used only when a plan has no case rate for that code. The pairs with both are listed in [`results/dual_basis.csv`](../results/dual_basis.csv).
4. **Commercial comparisons use case rates only.** Medicare Advantage and Medicaid plans are almost all paid by fee schedule tied to government rates, so every basis is kept for them.
5. **Duplicate lines.** Some hospitals repeat a rate once per revenue code. Repeats are collapsed to their median. 244 of 9,903 rates had repeats that disagreed (reported by validation check 10).

## Medicare benchmark

[`src/build_medicare_benchmark.py`](../src/build_medicare_benchmark.py):

- National OPPS payment rate by HCPCS from the **October 2026 Addendum B** (for example, 45378 maps to APC 5311 at $950.10).
- Each hospital's **FY 2026 wage index** from IPPS final rule Table 2 (OPPS uses the IPPS wage index). All 10 hospitals are in CBSA 35614 with a wage index of **1.3697**.
- Adjusted rate = national rate × (0.60 × wage index + 0.40), so 45378 = $950.10 × 1.2218 = **$1,160.85**.

The benchmark is a single-procedure facility payment. It ignores multiple-procedure discounting and the beneficiary's coinsurance split, neither of which changes the total Medicare-allowed amount for a single procedure.

## Payer families and segments

[`src/classify_payers.py`](../src/classify_payers.py) maps 623 payer/plan name pairs with ordered regex rules. Every label records the rule that produced it ([`data/reference/payer_map.csv`](../data/reference/payer_map.csv)).

- **Families** roll subsidiaries up to the parent: Oxford and "UHC Empire" (the NYS Empire Plan, administered by UnitedHealthcare) → UnitedHealthcare; HealthPlus → Anthem / Empire BCBS; GHI, HIP, and ConnectiCare → EmblemHealth.
- **Segments:** Commercial, Medicare Advantage, Medicaid managed care (including Child Health Plus, HARP, PACE, FIDA), NY Essential Plan, Exchange, Rental network (MultiPlan, PHCS, MagnaCare, First Health, and similar), Behavioral carve-out, Government (VA/Tricare), Traditional Medicare, Self-pay, Out-of-network.
- Rental networks are their own family because the employer or administrator rents the hospital's discount; there is no insurer behind the rate.

## Insurer index

For each hospital and code with at least 3 commercial case rates, compute the median commercial rate. Divide every commercial plan's rate by that median, then take each insurer family's median ratio across all its hospital/code pairs. Families present at fewer than 3 hospitals are dropped. An index of 1.47 means the insurer's rates run 47% above the typical commercial rate at the same hospitals for the same procedures.

## Validation and tests

- [`sql/02_validation.sql`](../sql/02_validation.sql): 10 checks run on every build. Any failure stops the pipeline. Results: [`results/validation.csv`](../results/validation.csv).
- [`tests/test_pipeline.py`](../tests/test_pipeline.py): re-reads one file of each format (wide CSV, tall CSV, JSON) with a separate code path and confirms the database value, plus 8 payer classification cases.

## Known limits

- Rates are contract terms, not paid claims or volumes.
- Facility fees only; the gastroenterologist's and anesthesiologist's fees are separate bills.
- St. Joseph's publishes no commercial case rates, so it is excluded from the commercial hospital and insurer comparisons.
- A plan name like "All Commercial Plans" (NYP) can cover many products that other hospitals list separately, so plan counts are not comparable across hospitals.
