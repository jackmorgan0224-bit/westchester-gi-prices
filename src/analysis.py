"""Price analysis: what Westchester hospitals negotiate for GI endoscopy, by payer and segment.

All comparisons use published negotiated dollar amounts only (data/gi_prices.duckdb,
table `negotiated`). Percentage and algorithm rates are counted but never converted to
dollars here, and no blanks are filled. Prices are expressed as a multiple of what
traditional Medicare pays the same hospital for the same code (OPPS, wage-adjusted), which
puts a $950 procedure and a $1,960 procedure on one scale.

Commercial comparisons use case rates only (one price for the whole outpatient visit).
Fee-schedule lines price a single chargemaster line, so mixing them in would compare a
whole visit at one hospital with one line of the bill at another. Medicare Advantage and
Medicaid plans are almost all paid by fee schedule tied to government rates, so every
basis is kept for them. The `headline` view below applies that rule.

Outputs in results/:
- segment_summary.csv        each code x segment: median % of Medicare across all plans
- commercial_by_hospital.csv each core code x hospital: commercial median, low, high, spread
- payer_index.csv            like-for-like insurer comparison (same hospital, same code)
- chargemaster.csv           gross charge and cash price vs. Medicare, by hospital x code
- dual_basis.csv             plans that publish both a case rate and a fee-schedule line
- coverage.csv               how many rows had a usable dollar amount, by hospital
"""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MIN_HOSPITALS_FOR_INDEX = 3

HEADLINE_VIEW = """
    CREATE OR REPLACE TEMP VIEW headline AS
    SELECT * FROM negotiated
    WHERE core AND (segment <> 'Commercial' OR price_basis = 'case rate')
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
    # Like-for-like: divide each commercial plan's rate by the median commercial rate for the
    # same hospital and code, so hospital price levels and procedure mix cancel out. A payer
    # with index 1.20 pays 20% more than the typical commercial plan at the same hospitals.
    "payer_index": """
        WITH base AS (
            SELECT hospital_id, code, median(negotiated_dollar) AS hosp_code_median
            FROM headline WHERE segment = 'Commercial'
            GROUP BY ALL HAVING count(*) >= 3
        ),
        rel AS (
            SELECT n.payer_family, n.hospital_id, n.code, n.negotiated_dollar / b.hosp_code_median AS rel
            FROM headline n JOIN base b USING (hospital_id, code)
            WHERE n.segment = 'Commercial'
        )
        SELECT payer_family,
               count(DISTINCT hospital_id) AS hospitals,
               count(*) AS plan_code_rates,
               round(median(rel), 2) AS index_vs_typical_commercial,
               round(quantile_cont(rel, 0.25), 2) AS p25,
               round(quantile_cont(rel, 0.75), 2) AS p75
        FROM rel
        GROUP BY ALL
        HAVING count(DISTINCT hospital_id) >= {min_h}
        ORDER BY index_vs_typical_commercial DESC
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
