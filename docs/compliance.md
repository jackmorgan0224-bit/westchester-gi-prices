# Compliance findings

**Short answer:** all 10 Westchester hospitals publish a current file in CMS's 2026 (v3.0) format, and their colonoscopy, EGD, and EUS rows pass every conditional requirement I tested. Where the files fall short is usability: hundreds of rates are written as a percent of the visit's billed charges with no way in the file to estimate those charges, and one hospital's percentages appear to be missing their decimal points.

## Why these checks are hand-written

CMS publishes an open-source validator, but the current npm release (`hpt-validator` 1.11.1, CLI 1.7.1) only includes schemas for template versions 1.1 and 2.0, and the CLI accepts only "v2.0". Every Westchester file is v3.0.0. So [`src/compliance.py`](../src/compliance.py) implements the rules directly from the [CMS v3.0 data dictionary](https://github.com/CMSgov/hospital-price-transparency/tree/master/documentation), citing the rule number for each check. Row-level checks cover the 20,377 GI rows only, so they describe how each hospital handled these procedures, not its entire file.

## File-level checks: all pass

| Check | Rule | Result |
|---|---|---|
| Location listed in the hospital's `cms-hpt.txt`, with a contact | 45 CFR 180.50(d)(6) | 10 of 10 |
| Template version 3.0.0 | v3.0 data dictionary (required from Jan 1, 2026; enforced from Apr 1) | 10 of 10 |
| Updated within the last 12 months | annual update requirement | 10 of 10 (newest 27 days old, oldest 212) |
| Attestation confirmed, attester named | v3.0 general data elements | 10 of 10 |
| Type 2 organizational NPI listed | v3.0 general data elements | 10 of 10 |

A correction worth recording: the first copy of Westchester Medical Center's file I found (via a third-party aggregator) was `wmchealth.org/wp-content/uploads/2025/06/133964321_WestchesterMedicalCenter_standardcharges.csv`, a template v2.1.0 file whose `last_updated_on` is 12/17/2024. That old file is still reachable, but the hospital's `cms-hpt.txt` index points to a different, current file dated July 28, 2026. Reading the index rather than trusting a search result is the step that caught it.

## Row-level conditional requirements: 0 failures

| Check | CMS v3.0 rule | GI rows tested | Failing |
|---|---|---|---|
| A payer/plan row carries a negotiated charge | #1 | 20,377 | 0 |
| A negotiated charge has payer, plan, and methodology | #1 | 20,377 | 0 |
| Methodology "other" is explained in the notes | #4 | 1,478 | 0 |
| Each item has at least one charge | #5 | 20,377 | 0 |
| A dollar rate comes with de-identified min and max | #6 | 19,440 | 0 |
| A percentage/algorithm rate has a count of allowed amounts | #7 | 940 | 0 |
| ...and 10th / median / 90th percentile allowed amounts (unless count is 0) | #8 | 21 | 0 |
| A count of 0 is explained in the notes | #9 | 919 | 0 |
| Count is a whole number, or "1 through 10" for 1 to 10 | count format | 940 | 0 |

Most percentage rates report a count of 0 with the note "No services performed during 15-month lookback period," which is allowed and explains why the new 2026 percentile fields are mostly empty.

## Usability: where the files fall short

These are not format violations. They are about whether a patient could turn a published rate into an expected price, which is the purpose of the rule and the standard the attestation describes ("all necessary information available to the hospital for the public to be able to derive the dollar amount").

**Percent-of-charges rates.** A rate of "63% of total billed charges" applies to the whole claim for the visit: the procedure room, supplies, recovery, and anything else on the bill, most of which sits on chargemaster lines under other codes. So the gross charge on the procedure's own row would not be enough by itself, and these files offer no estimate of a typical visit's total charges. In 813 GI rows the hospital uses this method:

| Hospital | Percent-of-charges rates | ...no gross charge on the row | ...no gross charge for that code anywhere in the file | Percentages over 1,000% |
|---|---|---|---|---|
| Westchester Medical Center | 260 | 260 | 224 | **134** |
| Montefiore New Rochelle | 204 | 204 | 204 | 0 |
| NYP Westchester (system file) | 189 | 189 | 189 | 0 |
| Montefiore Mount Vernon | 116 | 116 | 104 | 0 |
| White Plains Hospital | 19 | 19 | 1 | 0 |
| St. John's Riverside | 25 | 0 | 0 | 0 |
| Other four hospitals | 0 | 0 | 0 | 0 |
| **Total** | **813** | **788** | **722** | **134** |

**The 6300% problem.** At Westchester Medical Center, 10 plans have percent-of-charges rates over 1,000%, all round hundreds: Emblem GHI/HIP (three products) at 6300, Emblem Select Care 5400, MultiPlan 7500, PHCS 8500, Cigna PPO 7000, MagnaCare Standard 7000, MagnaCare Preferred 5500, and CDPHP 5000. In the same file, other percent-of-charges plans are listed at 75, 85, and 100 (plus self-pay discounts at 30 and 50). The large values are very likely 63%, 54%, 75%, and so on entered without a decimal point. As published, they say the plan pays 63 times the hospital's charges.

## Other data questions

- **Westchester Medical Center, "MEDICARE" rows.** Rows on revenue code 360 run 2.75x to 3.6x Medicare's published rate for that hospital: $4,069 for a diagnostic colonoscopy (Medicare: $1,161), $4,111 for a polyp removal ($1,494), $4,066 for an EGD ($1,132). Its EUS rows ($2,384) and its EGD lines on revenue code 450 ($1,127 for both 43235 and 43239) match Medicare within 1%. These may represent something other than the Medicare payment for the procedure; it is a question for the hospital, not a confirmed error.
- **Two prices for one procedure.** White Plains Hospital lists two plans (HealthFirst Essential Plan 3 & 4 and Elderplan Medicare) twice for the same codes: a whole-visit case rate and a single-line fee schedule, a median 5.6x apart across 38 plan/code pairs. Montefiore Mount Vernon does the same for 4 pairs. Westchester Medical Center lists 30 such pairs across 10 plans: for 4 UnitedHealthcare plans (Commercial, Compass, Empire Plan, Exchange) the case rate is about 2.8x the line amount, for 2 MagnaCare networks the two match, and for 4 behavioral carve-out plans (Beacon, Value Options) the case rate is a small fraction of the line amount. A patient comparing prices would see two very different numbers for the same plan.
- **System-wide files.** NYP Westchester (Bronxville) shares one file with NYP's Manhattan and Brooklyn campuses under a single license, so its rates can't be distinguished from theirs.

## Can anyone profit from catching these?

Not through a bounty. CMS takes complaints through a public form and enforces with warning letters, corrective action plans, and fines, but fines go to the government. The practical value is to the hospitals themselves (a cheap pre-audit before CMS reviews the same file) and to anyone who needs to read these files correctly.

Full results: [`results/compliance_file_checks.csv`](../results/compliance_file_checks.csv), [`results/compliance_row_checks.csv`](../results/compliance_row_checks.csv), [`results/compliance_examples.csv`](../results/compliance_examples.csv).
