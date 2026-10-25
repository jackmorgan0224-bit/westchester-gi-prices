-- Build the analysis tables from data/gi_rows.csv and the reference files.
-- Run by src/build_db.py from the repo root.

CREATE OR REPLACE TABLE hospitals AS
SELECT * FROM read_csv('data/reference/hospitals.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE gi_codes AS
SELECT code, family, label, core::INT = 1 AS core
FROM read_csv('data/reference/gi_codes.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE medicare AS
SELECT hospital_id, code, status_indicator, apc, national_rate::DOUBLE AS national_rate,
       wage_index::DOUBLE AS wage_index, medicare_rate::DOUBLE AS medicare_rate
FROM read_csv('data/reference/medicare_opps_2026.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE payer_map AS
SELECT * FROM read_csv('data/reference/payer_map.csv', header = true, all_varchar = true);

-- Every extracted row, values exactly as published (strings), plus typed copies.
-- try_cast leaves non-numeric text (e.g. "1 through 10") as NULL in the typed column;
-- the raw string stays alongside for the compliance checks.
CREATE OR REPLACE TABLE raw_rows AS
SELECT row_number() OVER () AS row_id, *
FROM read_csv('data/gi_rows.csv', header = true, all_varchar = true);

CREATE OR REPLACE TABLE rows_typed AS
SELECT
    r.*,
    try_cast(replace(r.gross_charge, ',', '') AS DOUBLE)          AS gross_num,
    try_cast(replace(r.discounted_cash, ',', '') AS DOUBLE)       AS cash_num,
    try_cast(replace(r.min_negotiated, ',', '') AS DOUBLE)        AS min_num,
    try_cast(replace(r.max_negotiated, ',', '') AS DOUBLE)        AS max_num,
    try_cast(replace(r.negotiated_dollar, ',', '') AS DOUBLE)     AS dollar_num,
    try_cast(replace(r.negotiated_percentage, ',', '') AS DOUBLE) AS pct_num,
    try_cast(replace(r.median_amount, ',', '') AS DOUBLE)         AS median_num,
    try_cast(replace(r.p10_amount, ',', '') AS DOUBLE)            AS p10_num,
    try_cast(replace(r.p90_amount, ',', '') AS DOUBLE)            AS p90_num,
    coalesce(lower(trim(r.setting)), '')       AS setting_l,
    coalesce(lower(trim(r.billing_class)), '') AS billing_class_l,
    coalesce(lower(trim(r.methodology)), '')   AS methodology_l,
    coalesce(pm.payer_family, '') AS payer_family,
    coalesce(pm.segment, '')      AS segment,
    g.family AS proc_family, g.label, g.core
FROM raw_rows r
LEFT JOIN payer_map pm USING (hospital_id, payer_name, plan_name)
JOIN gi_codes g USING (code);

-- Rows used for price comparisons: the facility (hospital) charge for an outpatient
-- procedure with no modifier. Professional (physician) lines and inpatient lines are
-- excluded because Medicare's OPPS benchmark covers the outpatient facility fee only.
CREATE OR REPLACE TABLE price_rows AS
SELECT *
FROM rows_typed
WHERE setting_l IN ('outpatient', 'both')
  AND billing_class_l IN ('facility', '')
  AND coalesce(trim(modifiers), '') = '';

-- One negotiated dollar amount per hospital x code x payer x plan.
-- Several hospitals publish two kinds of rows for the same procedure and plan:
--   * a case rate: one price for the whole outpatient visit (room, supplies, recovery)
--   * a fee-schedule line: the price of a single chargemaster line, often one of several
--     lines that make up the visit
-- The case rate is the closer match to Medicare's OPPS payment, which also bundles the
-- visit into one APC payment, so when both exist we use the case rate. Fee-schedule
-- (and other) rows are used only when a plan has no case rate for that code.
-- Repeated lines with the same basis (e.g. one per revenue code) are collapsed to their
-- median; n_distinct_values records when those disagreed.
CREATE OR REPLACE TABLE negotiated AS
WITH ranked AS (
    SELECT *,
           CASE methodology_l WHEN 'case rate' THEN 1 WHEN 'fee schedule' THEN 2 ELSE 3 END AS basis_rank
    FROM price_rows
    WHERE dollar_num > 0
),
best AS (
    SELECT hospital_id, code, payer_name, plan_name, min(basis_rank) AS basis_rank
    FROM ranked
    GROUP BY ALL
)
SELECT
    r.hospital_id, r.code, r.proc_family, r.label, r.core, r.payer_name, r.plan_name,
    r.payer_family, r.segment,
    CASE b.basis_rank WHEN 1 THEN 'case rate' WHEN 2 THEN 'fee schedule' ELSE 'other' END AS price_basis,
    median(r.dollar_num) AS negotiated_dollar,
    count(DISTINCT r.dollar_num) AS n_distinct_values,
    m.medicare_rate,
    median(r.dollar_num) / m.medicare_rate AS pct_of_medicare
FROM ranked r
JOIN best b USING (hospital_id, code, payer_name, plan_name, basis_rank)
JOIN medicare m USING (hospital_id, code)
GROUP BY r.hospital_id, r.code, r.proc_family, r.label, r.core, r.payer_name, r.plan_name,
         r.payer_family, r.segment, b.basis_rank, m.medicare_rate;

-- Plans that publish BOTH a case rate and a fee-schedule line for the same code
-- (reported, because a shopper sees two different "prices" for one procedure).
CREATE OR REPLACE TABLE dual_basis AS
SELECT hospital_id, code, payer_name, plan_name, payer_family, segment,
       median(dollar_num) FILTER (WHERE methodology_l = 'case rate')    AS case_rate,
       median(dollar_num) FILTER (WHERE methodology_l = 'fee schedule') AS fee_schedule_line
FROM price_rows
WHERE dollar_num > 0
GROUP BY ALL
HAVING case_rate IS NOT NULL AND fee_schedule_line IS NOT NULL;

-- Per hospital x code item-level charges (gross, cash, de-identified min/max).
CREATE OR REPLACE TABLE item_charges AS
SELECT
    p.hospital_id, p.code, p.proc_family, p.label, p.core,
    median(p.gross_num) AS gross_charge,
    median(p.cash_num)  AS discounted_cash,
    median(p.min_num)   AS min_negotiated,
    median(p.max_num)   AS max_negotiated,
    count(DISTINCT p.gross_num) AS n_distinct_gross,
    m.medicare_rate
FROM price_rows p
JOIN medicare m USING (hospital_id, code)
GROUP BY p.hospital_id, p.code, p.proc_family, p.label, p.core, m.medicare_rate;
