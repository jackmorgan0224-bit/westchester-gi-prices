# Memo: GI endoscopy prices at Westchester hospitals

**To:** a managed care or network strategy team
**Re:** what the 2026 hospital price files show for colonoscopy, EGD, and EUS in Westchester County
**Data:** 10 hospital price files downloaded Oct 25, 2026; 9,903 negotiated dollar rates; Medicare OPPS benchmark (Oct 2026, wage-adjusted)

## Bottom line

For a commercial plan, the price of a routine colonoscopy in Westchester depends far more on **which hospital** and **which insurer contract** than on the procedure itself. The median commercial case rate is about 4x Medicare, but it runs from roughly 1x at St. John's Riverside to nearly 6x at NYP Westchester and White Plains Hospital. Medicare Advantage rates cluster tightly around traditional Medicare; Medicaid pays less than Medicare.

## 1. Line of business

| Diagnostic colonoscopy (45378) | Median rate | Multiple of Medicare | Middle half |
|---|---|---|---|
| Commercial (case rates) | $4,724 | 4.1x | 2.7x to 5.8x |
| Exchange (individual market) | $1,637 | 1.4x | 1.1x to 2.6x |
| NY Essential Plan | $1,602 | 1.4x | 0.9x to 1.9x |
| Medicare Advantage | $1,155 | 1.0x | 0.9x to 1.0x |
| Medicaid managed care | $917 | 0.8x | 0.7x to 0.9x |

Medicare for this code at these hospitals: **$1,161**. Of the five segments in this table, commercial pays the most and Medicaid the least for every one of the 11 codes studied. Medicare Advantage rates sit within a few percent of traditional Medicare almost everywhere, consistent with contracts priced at or near 100% of Medicare. Medicaid pays least for the complex procedures: **0.37x** Medicare for an upper EUS.

## 2. Hospital

Median commercial case rate for a diagnostic colonoscopy:

| Hospital | Median | Plans | Multiple of Medicare |
|---|---|---|---|
| NYP Westchester | $6,803 | 7 | 5.9x |
| White Plains Hospital | $6,750 | 15 | 5.8x |
| Westchester Medical Center | $6,354 | 11 | 5.5x |
| Montefiore Mount Vernon | $5,669 | 17 | 4.9x |
| Montefiore New Rochelle | $4,939 | 12 | 4.3x |
| NYP Hudson Valley | $4,463 | 6 | 3.8x |
| Phelps (Northwell) | $3,108 | 21 | 2.7x |
| Northern Westchester (Northwell) | $3,108 | 21 | 2.7x |
| St. John's Riverside | $1,322 | 11 | 1.1x |

The two Northwell hospitals publish identical commercial rates, consistent with system-level contracting. The spread within a hospital is also wide: at Montefiore New Rochelle the same procedure ranges from $3,549 to $18,107 depending on the plan. St. Joseph's is not ranked because it publishes no commercial case rates; its single-line commercial rates (about $1,491) would place it second lowest.

**So what:** for a plan steering members to lower-cost sites, moving a colonoscopy from a ~$6,500 hospital to a ~$3,100 one saves more than the entire Medicare payment for the procedure.

## 3. Insurer

To compare insurers fairly, each insurer's rate at a hospital is divided by the typical (median) insurer's rate at the same hospital for the same code. That cancels out hospital price level and procedure mix. Hospitals list very different numbers of products per insurer (Northwell lists five UnitedHealthcare/Oxford products with identical rates; NYP lists one "All Commercial Plans" row), so how products are counted matters. Three ways:

| Insurer | Hospitals | Each insurer once per hospital and code (used in the chart) | Each hospital weighted equally | Every product row counted |
|---|---|---|---|---|
| EmblemHealth | 8 | 1.51 | 1.17 | 1.00 |
| UnitedHealthcare (incl. Oxford) | 9 | 1.16 | 1.23 | 1.47 |
| Cigna | 5 | 1.16 | 1.17 | 1.25 |
| Anthem / Empire BCBS | 9 | 1.00 | 1.00 | 0.96 |
| Aetna | 7 | 0.97 | 1.00 | 1.00 |
| Oscar | 3 | 0.73 | 0.73 | 0.76 |
| MVP | 4 | 0.61 | 0.58 | 0.62 |

**What holds under every method:** UnitedHealthcare and Cigna pay above the typical insurer; Anthem and Aetna sit at the norm; Oscar and MVP pay roughly 25% to 40% less. Emblem is above the norm under two of the three methods. The exact order at the top is not stable, so I wouldn't claim any one insurer "pays the most."

**So what:** for a hospital renegotiating, the MVP and Oscar contracts are the clearest candidates to raise. For an employer choosing a carrier, the same procedure at the same hospital can cost 15% to 50% more through a high-paying carrier than through the typical one.

## 4. Flat case rates

Medicare pays more for harder procedures: $1,161 for a diagnostic colonoscopy, $1,494 for one with polyp removal (+29%), and $2,395 for an upper EUS. Commercial contracts often don't. **84 of 113** commercial plans pay exactly the same case rate for a diagnostic colonoscopy and a polyp removal, and at Phelps and Northern Westchester the median commercial case rate is the same $3,352 for an EGD with biopsy, a polyp removal, and an upper EUS.

**So what:** commercial "multiples of Medicare" look lower for EUS (2.8x) than for colonoscopy (4.1x) because many contracts price every endoscopy visit the same, while Medicare pays about twice as much for EUS. Under flat case rates, complex endoscopy earns the hospital less per procedure, relative to Medicare's weights, than routine colonoscopy does.

## Questions I'd want answered before acting

1. Westchester Medical Center's "MEDICARE" rows on revenue code 360 run 2.75x to 3.6x Medicare's published rate for that hospital (for example $4,069 for a diagnostic colonoscopy vs. $1,161), while its EUS rows and its EGD lines on revenue code 450 match Medicare within 1%. What do the revenue code 360 lines represent?
2. White Plains Hospital lists two prices for the same code for two plans (HealthFirst Essential Plan 3 & 4 and Elderplan Medicare): a case rate and a much lower single-line fee schedule, a median 5.6x apart. Which one does a patient's cost estimate use?
3. How is a patient meant to estimate the "percent of billed charges" contracts (for example Emblem, MultiPlan, and PHCS at Westchester Medical Center), when the file doesn't show what total charges for an endoscopy visit typically are?

See [compliance findings](compliance.md) for the full list of file issues.
