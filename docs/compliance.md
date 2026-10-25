# Compliance findings

**Short answer:** all 10 Westchester hospitals publish a current file in CMS's 2026 (v3.0) format, and their colonoscopy, EGD, and EUS rows pass every conditional requirement I tested. The problems are about usability, not format: for five hospitals, a large share of percentage-based rates can't be turned into a dollar amount, which is the standard each hospital signs in its attestation.

## Why these checks are hand-written

CMS publishes an open-source validator, but the current npm release (`hpt-validator` 1.11.1, CLI 1.7.1) only supports the v2.0 template. Every Westchester file is v3.0.0. So [`src/compliance.py`](../src/compliance.py) implements the rules directly from the [CMS v3.0 data dictionary](https://github.com/CMSgov/hospital-price-transparency/tree/master/documentation), citing the rule number for each check. Row-level checks cover the 20,377 GI rows only, so they describe how each hospital handled these procedures, not its entire file.

## File-level checks: all pass

| Check | Rule | Result |
|---|---|---|
| Location listed in the hospital's `cms-hpt.txt`, with a contact | 45 CFR 180.50(d)(6) | 10 of 10 |
| Template version 3.0.0 | v3.0 data dictionary (required from Jan 1, 2026; enforced from Apr 1) | 10 of 10 |
| Updated within the last 12 months | annual update requirement | 10 of 10 (newest 27 days old, oldest 212) |
| Attestation confirmed, attester named | v3.0 general data elements | 10 of 10 |
| Type 2 organizational NPI listed | v3.0 general data elements | 10 of 10 |

A correction worth recording: the first copy of Westchester Medical Center's file I found (through a third-party aggregator) was dated December 2024. That was an old file still hosted at an outdated address. The hospital's `cms-hpt.txt` index points to a current file dated July 28, 2026. Reading the index rather than trusting a search result is the step that caught it.

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

The attestation each hospital signs says that when a rate can't be shown in dollars, the hospital "has provided all necessary information available to the hospital for the public to be able to derive the dollar amount." Two checks test that.

| Hospital | Percent-of-charges rates | ...with no gross charge on the row | ...and no gross charge for that code anywhere in the file | Percentages over 1,000% |
|---|---|---|---|---|
| Westchester Medical Center | 260 | 260 | 224 | **134** |
| Montefiore New Rochelle | 204 | 204 | 204 | 0 |
| NYP Westchester (system file) | 189 | 189 | 189 | 0 |
| Montefiore Mount Vernon | 116 | 116 | 104 | 0 |
| White Plains Hospital | 19 | 19 | 1 | 0 |
| Other five hospitals | 25 | 0 | 0 | 0 |
| **Total** | **813** | **788** | **722** | **134** |

**What this means for a patient.** A rate of "63% of total billed charges" is only useful if you know the billed charges. For 722 of these rates, the hospital publishes no gross charge for that procedure at all, so there is nothing to multiply.

**The 6300% problem.** Westchester Medical Center lists Emblem plans at "6300," MultiPlan at "7500," and PHCS at "8500" percent of billed charges, in the same file where other plans are listed at "75" and "85." These are almost certainly 63%, 75%, and 85% entered without a decimal point. As published, they say the plan pays 63 times the hospital's charges.

## Other data questions

- **Westchester Medical Center, traditional Medicare.** The file lists $4,069 for a diagnostic colonoscopy under "MEDICARE." Medicare's own rate for that hospital is $1,161. The same file's EUS rows for Medicare ($2,384) match Medicare's rate within 0.5%, which suggests the colonoscopy rows are wrong rather than the method.
- **Two prices for one procedure.** White Plains Hospital and Montefiore Mount Vernon list some plans twice for the same code: a whole-visit case rate and a single-line fee schedule. At White Plains the case rate is a median **5.6x** the line amount (38 plan/code pairs). A patient comparing prices would see two very different numbers for the same plan.
- **System-wide files.** NYP Westchester (Bronxville) shares one file with NYP's Manhattan and Brooklyn campuses under a single license, so its rates can't be distinguished from theirs.

## Can anyone profit from catching these?

Not through a bounty. CMS takes complaints through a public form and enforces with warning letters, corrective action plans, and fines, but fines go to the government. The practical value is to the hospitals themselves (a cheap pre-audit before CMS finds the same issues) and to anyone who needs to read these files correctly.

Full results: [`results/compliance_file_checks.csv`](../results/compliance_file_checks.csv), [`results/compliance_row_checks.csv`](../results/compliance_row_checks.csv), [`results/compliance_examples.csv`](../results/compliance_examples.csv).
