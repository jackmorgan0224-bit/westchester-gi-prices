-- Validation checks. Each returns one row: check name, PASS/FAIL, detail.
-- src/build_db.py runs these after 01_build.sql and stops the build on any FAIL.

-- 1. Every hospital in the reference list made it through extraction
SELECT 'all 10 hospitals extracted' AS check_name,
       CASE WHEN count(DISTINCT r.hospital_id) = (SELECT count(*) FROM hospitals) THEN 'PASS' ELSE 'FAIL' END AS status,
       count(DISTINCT r.hospital_id) || ' of ' || (SELECT count(*) FROM hospitals) AS detail
FROM raw_rows r;

-- 2. No rows lost when joining to the code list (every extracted code is a target code)
SELECT 'no rows lost joining to gi_codes',
       CASE WHEN (SELECT count(*) FROM rows_typed) = (SELECT count(*) FROM raw_rows) THEN 'PASS' ELSE 'FAIL' END,
       (SELECT count(*) FROM rows_typed) || ' of ' || (SELECT count(*) FROM raw_rows);

-- 3. Every payer/plan name is classified
SELECT 'every payer/plan has a family and segment',
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       count(*) || ' unclassified rows'
FROM rows_typed WHERE payer_name IS NOT NULL AND (payer_family = '' OR segment = '');

-- 4. Medicare benchmark exists for every hospital x code
SELECT 'Medicare benchmark for every hospital x code',
       CASE WHEN count(*) = (SELECT count(*) FROM hospitals) * (SELECT count(*) FROM gi_codes) THEN 'PASS' ELSE 'FAIL' END,
       count(*) || ' rows'
FROM medicare;

-- 5. Benchmark spot check against Addendum B: 45378 national rate $950.10, Westchester wage index 1.3697
SELECT 'benchmark 45378 = 950.10 x (0.6 x 1.3697 + 0.4)',
       CASE WHEN bool_and(abs(medicare_rate - round(950.10 * (0.6 * 1.3697 + 0.4), 2)) < 0.01) THEN 'PASS' ELSE 'FAIL' END,
       any_value(medicare_rate)::VARCHAR
FROM medicare WHERE code = '45378';

-- 6. negotiated is unique on its key
SELECT 'negotiated unique per hospital x code x payer x plan',
       CASE WHEN count(*) = count(DISTINCT (hospital_id, code, payer_name, plan_name)) THEN 'PASS' ELSE 'FAIL' END,
       count(*) || ' rows'
FROM negotiated;

-- 7. Dollar amounts are positive and multiples of Medicare are finite
SELECT 'negotiated dollars positive, multiples finite',
       CASE WHEN count(*) FILTER (WHERE negotiated_dollar <= 0 OR NOT isfinite(pct_of_medicare)) = 0 THEN 'PASS' ELSE 'FAIL' END,
       min(negotiated_dollar)::VARCHAR || ' to ' || max(negotiated_dollar)::VARCHAR
FROM negotiated;

-- 8. Every hospital contributes core-code rates in the two big segments
SELECT 'each hospital has Medicare Advantage and Medicaid/commercial rates',
       CASE WHEN count(*) = (SELECT count(*) FROM hospitals) THEN 'PASS' ELSE 'FAIL' END,
       count(*) || ' hospitals'
FROM (
    SELECT hospital_id FROM negotiated WHERE core
    GROUP BY 1
    HAVING count(*) FILTER (WHERE segment = 'Medicare Advantage') > 0
       AND count(*) FILTER (WHERE segment IN ('Commercial', 'Medicaid managed care')) > 0
);

-- 9. Typed numbers parsed: no row has a dollar string that failed to convert
SELECT 'every published dollar amount parsed as a number',
       CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL' END,
       count(*) || ' unparsed'
FROM rows_typed WHERE negotiated_dollar IS NOT NULL AND dollar_num IS NULL;

-- 10. Disagreeing duplicate lines are rare (reported, not fatal above 0, fatal above 5%)
SELECT 'duplicate lines that disagree are under 5% of rates',
       CASE WHEN avg((n_distinct_values > 1)::INT) < 0.05 THEN 'PASS' ELSE 'FAIL' END,
       sum((n_distinct_values > 1)::INT) || ' of ' || count(*) || ' rates (median used)'
FROM negotiated;
