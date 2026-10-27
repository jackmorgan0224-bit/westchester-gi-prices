"""Price analysis: what Westchester hospitals negotiate for GI endoscopy, by payer and segment.

All comparisons use published negotiated dollar amounts only (data/gi_prices.duckdb,
table `negotiated`). Percentage and algorithm rates are counted but never converted to
dollars here, and no blanks are filled. Prices are expressed as a multiple of what
traditional Medicare pays the same hospital for the same code (OPPS, wage-adjusted), which
puts a $950 procedure and a $1,960 procedure on one scale.

Commercial and Exchange comparisons use case rates only (one price for the whole
outpatient visit). Fee-schedule lines price a single chargemaster line, so mixing them in
would compare a whole visit at one hospital with one line of the bill at another. Exchange
products are commercial products sold on the individual market, so they get the same rule;
with every basis kept, the Exchange colonoscopy median was 1.4x Medicare, but its case
rates alone are 2.7x. Medicare Advantage, Medicaid, and Essential Plan products are almost
all paid by fee schedule tied to government rates, so every basis is kept for them. The
`headline` view below applies that rule.

Outputs in results/:
- segment_summary.csv        each code x segment: median % of Medicare across all plans
- commercial_by_hospital.csv each core code x hospital: commercial median, low, high, spread
- payer_index.csv            like-for-like insurer comparison (same hospital, same code)
- payer_index_sensitivity.csv the insurer index under three ways of counting plans
- chargemaster.csv           gross charge and cash price vs. Medicare, by hospital x code
- dual_basis.csv             plans that publish both a case rate and a fee-schedule line
- coverage.csv               how many rows had a usable dollar amount, by hospital
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MIN_HOSPITALS_FOR_INDEX = 3
# Segments compared on whole-visit case rates only (see module docstring)
CASE_RATE_SEGMENTS = "('Commercial', 'Exchange (individual/small group)')"
CASE_RATE_RULE = f"(segment NOT IN {CASE_RATE_SEGMENTS} OR price_basis = 'case rate')"

HEADLINE_VIEW = f"""
    CREATE OR REPLACE TEMP VIEW headline AS
    SELECT * FROM negotiated
    WHERE core AND {CASE_RATE_RULE}
"""

QUERIES = {
    "segment_summary": """
        SELECT proc_family, code, label, segment,
               count(DISTINCT hospital_id) AS hospitals,
               count(*) AS plan_rates,
               round(median(negotiated_dollar), 0) AS median_dollar,
               round(median(pct_of_medicare), 2) AS median_x_medicare,
               round(quantile_cont(pct_of_medicare, 0.25), 2) AS p25_x_medicare,
               round(quantile_cont(pct_of_medicare, 0.75), 2) AS p75_x_medicare
        FROM headline
        GROUP BY ALL
        ORDER BY proc_family, code, median_x_medicare DESC
    """,
    "commercial_by_hospital": """
        SELECT n.hospital_id, h.hospital_name, n.proc_family, n.code, n.label,
               count(*) AS commercial_plans,
               string_agg(DISTINCT n.price_basis, ', ' ORDER BY n.price_basis) AS price_basis,
               round(median(n.negotiated_dollar), 0) AS median_dollar,
               round(min(n.negotiated_dollar), 0) AS low_dollar,
               round(max(n.negotiated_dollar), 0) AS high_dollar,
               round(max(n.negotiated_dollar) / min(n.negotiated_dollar), 1) AS high_low_ratio,
               any_value(n.medicare_rate) AS medicare_rate,
               round(median(n.pct_of_medicare), 2) AS median_x_medicare
        FROM headline n JOIN hospitals h USING (hospital_id)
        WHERE n.segment = 'Commercial'
        GROUP BY ALL
        ORDER BY n.code, median_dollar DESC
    """,
    # Like-for-like insurer comparison. Hospitals list very different numbers of products
    # per insurer (Northwell lists five UnitedHealthcare/Oxford products with identical rates;
    # NYP lists one "All Commercial Plans" row), so plan rows are first collapsed to one rate
    # per insurer x hospital x code (the median of that insurer's products). Each insurer's
    # rate is then divided by the median across insurers at the same hospital and code, which
    # cancels out hospital price level and procedure mix. Index 1.20 = 20% above the typical
    # insurer at the same hospitals for the same procedures.
    "payer_index": """
        WITH ins AS (
            SELECT hospital_id, code, payer_family, median(negotiated_dollar) AS dollar
            FROM headline WHERE segment = 'Commercial'
            GROUP BY ALL
        ),
        base AS (
            SELECT hospital_id, code, median(dollar) AS typical
            FROM ins GROUP BY ALL HAVING count(*) >= 3
        ),
        rel AS (
            SELECT i.payer_family, i.hospital_id, i.code, i.dollar / b.typical AS rel
            FROM ins i JOIN base b USING (hospital_id, code)
        )
        SELECT payer_family,
               count(DISTINCT hospital_id) AS hospitals,
               count(*) AS hospital_code_pairs,
               round(median(rel), 2) AS index_vs_typical_insurer,
               round(quantile_cont(rel, 0.25), 2) AS p25,
               round(quantile_cont(rel, 0.75), 2) AS p75
        FROM rel
        GROUP BY ALL
        HAVING count(DISTINCT hospital_id) >= {min_h}
        ORDER BY index_vs_typical_insurer DESC
    """.format(min_h=MIN_HOSPITALS_FOR_INDEX),
    # The same index under three ways of counting, because the top of the ranking depends on it
    "payer_index_sensitivity": """
        WITH plans AS (
            SELECT hospital_id, code, payer_family, negotiated_dollar AS dollar
            FROM headline WHERE segment = 'Commercial'
        ),
        ins AS (SELECT hospital_id, code, payer_family, median(dollar) AS dollar FROM plans GROUP BY ALL),
        base_plans AS (SELECT hospital_id, code, median(dollar) AS typical FROM plans GROUP BY ALL HAVING count(*) >= 3),
        base_ins AS (SELECT hospital_id, code, median(dollar) AS typical FROM ins GROUP BY ALL HAVING count(*) >= 3),
        by_plan AS (
            SELECT payer_family, median(dollar / typical) AS idx, count(DISTINCT hospital_id) AS hospitals
            FROM plans JOIN base_plans USING (hospital_id, code) GROUP BY 1
        ),
        rel_ins AS (SELECT payer_family, hospital_id, dollar / typical AS rel FROM ins JOIN base_ins USING (hospital_id, code)),
        by_insurer AS (
            SELECT payer_family, median(rel) AS idx, count(DISTINCT hospital_id) AS hospitals FROM rel_ins GROUP BY 1
        ),
        by_hospital AS (
            SELECT payer_family, median(r) AS idx FROM (
                SELECT payer_family, hospital_id, median(rel) AS r FROM rel_ins GROUP BY ALL
            ) GROUP BY 1
        )
        SELECT i.payer_family, i.hospitals,
               round(p.idx, 2) AS each_plan_row_counted,
               round(i.idx, 2) AS one_rate_per_insurer_hospital_code,
               round(h.idx, 2) AS each_hospital_weighted_equally
        FROM by_insurer i JOIN by_plan p USING (payer_family) JOIN by_hospital h USING (payer_family)
        WHERE i.hospitals >= {min_h}
        ORDER BY one_rate_per_insurer_hospital_code DESC
    """.format(min_h=MIN_HOSPITALS_FOR_INDEX),
    "chargemaster": """
        SELECT i.hospital_id, h.hospital_name, i.proc_family, i.code, i.label,
               i.gross_charge, i.discounted_cash, i.min_negotiated, i.max_negotiated, i.medicare_rate,
               round(i.gross_charge / i.medicare_rate, 2) AS gross_x_medicare,
               round(i.discounted_cash / i.medicare_rate, 2) AS cash_x_medicare,
               round(i.discounted_cash / i.gross_charge, 2) AS cash_share_of_gross
        FROM item_charges i JOIN hospitals h USING (hospital_id)
        WHERE i.core
        ORDER BY i.code, i.hospital_id
    """,
    "dual_basis": """
        SELECT d.*, round(case_rate / fee_schedule_line, 2) AS case_rate_x_line
        FROM dual_basis d JOIN gi_codes g USING (code)
        WHERE g.core
        ORDER BY hospital_id, code, payer_name
    """,
    "coverage": """
        SELECT hospital_id,
               count(*) AS gi_rows,
               count(*) FILTER (WHERE dollar_num > 0) AS rows_with_dollar,
               count(*) FILTER (WHERE dollar_num IS NULL AND pct_num IS NOT NULL) AS rows_percentage_only,
               count(*) FILTER (WHERE dollar_num IS NULL AND pct_num IS NULL AND negotiated_algorithm IS NOT NULL) AS rows_algorithm_only,
               count(*) FILTER (WHERE payer_name IS NULL) AS rows_no_payer,
               count(DISTINCT code) FILTER (WHERE core) AS core_codes_listed
        FROM rows_typed
        GROUP BY 1 ORDER BY 1
    """,
}


def main():
    RESULTS.mkdir(exist_ok=True)
    con = duckdb.connect(str(ROOT / "data" / "gi_prices.duckdb"), read_only=True)
    con.execute(HEADLINE_VIEW)
    for name, sql in QUERIES.items():
        path = RESULTS / f"{name}.csv"
        con.sql(sql).write_csv(str(path))
        n = con.sql(f"SELECT count(*) FROM read_csv('{path.as_posix()}')").fetchone()[0]
        print(f"wrote results/{name}.csv ({n} rows)")


if __name__ == "__main__":
    main()
