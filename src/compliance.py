"""Check each hospital's file against the CMS v3.0 rules, for the GI rows we use.

CMS's own validator (npm hpt-validator 1.11.1) only understands template v2.0, and every
Westchester file is v3.0.0, so these checks are written directly from the CMS v3.0 data
dictionary (github.com/CMSgov/hospital-price-transparency, documentation/CSV/README.md,
"Conditional Requirements"). Each check cites the rule it tests.

Two kinds of checks:
- File-level: header fields every v3.0 file must carry (date, version, attester, NPIs)
  and the cms-hpt.txt index entry.
- Row-level: the conditional requirements, applied to every GI row in data/gi_rows.csv.
  These are scoped to colonoscopy/EGD/EUS rows only, so they describe how a hospital
  handled these procedures, not its whole file.

Plus two "usability" checks that are not format violations but determine whether a
patient could actually turn the published rate into a dollar amount. That is the
standard each hospital signs in its attestation statement.

Outputs: results/compliance_file_checks.csv, results/compliance_row_checks.csv,
results/compliance_examples.csv
"""

import csv
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import duckdb
import ijson

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
DICT = "CMS v3.0 data dictionary"
COUNT_OK = re.compile(r"^(0|[1-9]\d*|1 through 10)$")


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def csv_header(path):
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        f = z.open(z.namelist()[0])
        lines = [f.readline().decode("utf-8-sig"), f.readline().decode("utf-8-sig")]
    else:
        with open(path, encoding="utf-8-sig") as f:
            lines = [f.readline(), f.readline()]
    keys, values = next(csv.reader([lines[0]])), next(csv.reader([lines[1]]))
    meta = {}
    for k, v in zip(keys, values):
        k = k.strip()
        if k.startswith("To the best of its knowledge"):
            meta["attestation_confirmed"] = v.strip().lower() == "true"
        elif k.startswith("license_number"):
            meta["license_number"] = v.strip()
        else:
            meta[k] = v.strip()
    return meta


def json_header(path):
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        f = z.open(z.namelist()[0])
    else:
        f = open(path, "rb")
    if f.peek(3)[:3] == b"\xef\xbb\xbf":
        f.read(3)
    meta, npis = {}, []
    for prefix, event, value in ijson.parse(f):
        if prefix == "standard_charge_information":
            break
        if prefix in ("version", "last_updated_on", "hospital_name"):
            meta[prefix] = value
        elif prefix == "attestation.attester_name":
            meta["attester_name"] = value
        elif prefix == "attestation.confirm_attestation":
            meta["attestation_confirmed"] = value is True
        elif prefix == "type_2_npi.item":
            npis.append(value)
        elif prefix == "license_information.license_number":
            meta["license_number"] = value
    meta["type_2_npi"] = "|".join(npis)
    f.close()
    return meta


def file_checks():
    manifest = list(csv.DictReader(open(RAW / "manifest.csv", encoding="utf-8")))
    rows = []
    for m in manifest:
        path = RAW / m["file"]
        is_json = path.suffix == ".json" or (path.suffix == ".zip" and zipfile.ZipFile(path).namelist()[0].lower().endswith(".json"))
        meta = json_header(path) if is_json else csv_header(path)
        downloaded = datetime.strptime(m["downloaded_utc"][:10], "%Y-%m-%d").date()
        updated = parse_date(meta.get("last_updated_on"))
        age = (downloaded - updated).days if updated else None
        checks = {
            "listed_in_cms_hpt_txt": True,  # fetch_mrfs.py fails if the location is missing
            "contact_in_cms_hpt_txt": m["index_contact_listed"] == "yes",
            "template_v3": (meta.get("version") or "").strip() == "3.0.0",
            "date_valid_format": updated is not None,
            "updated_within_12_months": age is not None and age <= 365,
            "attestation_confirmed": bool(meta.get("attestation_confirmed")),
            "attester_name_present": bool((meta.get("attester_name") or "").strip()),
            "type_2_npi_present": bool((meta.get("type_2_npi") or "").strip()),
        }
        rows.append({
            "hospital_id": m["hospital_id"], "format": "JSON" if is_json else "CSV",
            "version": (meta.get("version") or "").strip(), "last_updated_on": (meta.get("last_updated_on") or "").strip(),
            "days_old_at_download": age, "attester_name": (meta.get("attester_name") or "").strip(),
            **checks, "all_pass": all(checks.values()),
        })
    return rows


# Row-level checks: (id, rule source, description, SQL condition that marks a row as
# "in scope", SQL condition that marks an in-scope row as FAILING)
HAS_NEG = "(negotiated_dollar IS NOT NULL OR negotiated_percentage IS NOT NULL OR negotiated_algorithm IS NOT NULL)"
HAS_PAYER = "(payer_name IS NOT NULL OR plan_name IS NOT NULL)"
PCT_OR_ALG = "(negotiated_percentage IS NOT NULL OR negotiated_algorithm IS NOT NULL)"
HAS_NOTES = "(additional_payer_notes IS NOT NULL OR additional_generic_notes IS NOT NULL)"
ROW_CHECKS = [
    ("C1a", f"{DICT} #1", "A payer/plan row carries a negotiated charge (dollar, percentage, or algorithm)",
     HAS_PAYER, f"NOT {HAS_NEG}"),
    ("C1b", f"{DICT} #1", "A negotiated charge has a payer name, plan name, and methodology",
     HAS_NEG, "(payer_name IS NULL OR plan_name IS NULL OR methodology IS NULL)"),
    ("C4", f"{DICT} #4", "Methodology 'other' is explained in the notes",
     "methodology_l = 'other'", f"NOT {HAS_NOTES}"),
    ("C5", f"{DICT} #5", "Each item has at least one charge (gross, cash, or negotiated)",
     "TRUE", f"(gross_charge IS NULL AND discounted_cash IS NULL AND NOT {HAS_NEG})"),
    ("C6", f"{DICT} #6", "A negotiated dollar amount comes with the de-identified min and max",
     "negotiated_dollar IS NOT NULL", "(min_negotiated IS NULL OR max_negotiated IS NULL)"),
    ("C7", f"{DICT} #7", "A percentage or algorithm rate comes with a count of allowed amounts",
     PCT_OR_ALG, "allowed_count IS NULL"),
    ("C8", f"{DICT} #8", "A percentage or algorithm rate comes with 10th/median/90th percentile allowed amounts (unless count is 0)",
     f"{PCT_OR_ALG} AND coalesce(trim(allowed_count), '') <> '0'",
     "(p10_amount IS NULL OR median_amount IS NULL OR p90_amount IS NULL)"),
    ("C9", f"{DICT} #9", "A count of 0 allowed amounts is explained in the notes",
     "trim(allowed_count) = '0'", f"NOT {HAS_NOTES}"),
    ("C10", f"{DICT} (count format)", "Count of allowed amounts is a whole number, or exactly '1 through 10' for 1-10",
     "allowed_count IS NOT NULL", "NOT regexp_full_match(trim(allowed_count), '0|[1-9][0-9]*|1 through 10') OR regexp_full_match(trim(allowed_count), '[1-9]|10')"),
    ("U1", "Usability (attestation)", "A percent-of-charges rate can be turned into dollars: the item publishes a gross charge",
     "negotiated_percentage IS NOT NULL AND methodology_l = 'percent of total billed charges'", "gross_charge IS NULL"),
    ("U1b", "Usability (attestation)", "...and the hospital publishes a gross charge for that procedure code on at least one other row",
     "negotiated_percentage IS NOT NULL AND methodology_l = 'percent of total billed charges'",
     "(hospital_id, code) NOT IN (SELECT hospital_id, code FROM rows_typed WHERE gross_num > 0)"),
    ("U2", "Usability (plausibility)", "A percentage rate is plausible (at or below 1,000%)",
     "pct_num IS NOT NULL", "pct_num > 1000"),
]


def row_checks():
    con = duckdb.connect(str(ROOT / "data" / "gi_prices.duckdb"), read_only=True)
    out, examples = [], []
    hospitals = [r[0] for r in con.sql("SELECT DISTINCT hospital_id FROM rows_typed ORDER BY 1").fetchall()]
    for cid, source, desc, scope, fail in ROW_CHECKS:
        res = dict(con.sql(f"""
            SELECT hospital_id, struct_pack(n_scope := count(*), n_fail := count(*) FILTER (WHERE {fail}))
            FROM rows_typed WHERE {scope} GROUP BY 1
        """).fetchall())
        for h in hospitals:
            n_scope, n_fail = (res[h]["n_scope"], res[h]["n_fail"]) if h in res else (0, 0)
            out.append({"check_id": cid, "rule": source, "description": desc, "hospital_id": h,
                        "rows_in_scope": n_scope, "rows_failing": n_fail,
                        "pct_failing": round(100 * n_fail / n_scope, 1) if n_scope else None})
        for row in con.sql(f"""
            SELECT hospital_id, code, payer_name, plan_name, methodology, negotiated_dollar, negotiated_percentage,
                   gross_charge, allowed_count, median_amount
            FROM rows_typed WHERE {scope} AND ({fail})
            QUALIFY row_number() OVER (PARTITION BY hospital_id ORDER BY code, payer_name) = 1
        """).fetchall():
            examples.append(dict(zip(["hospital_id", "code", "payer_name", "plan_name", "methodology",
                                      "negotiated_dollar", "negotiated_percentage", "gross_charge",
                                      "allowed_count", "median_amount"], row), check_id=cid))
    return out, examples


def write(name, rows):
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote results/{name} ({len(rows)} rows)")


def main():
    write("compliance_file_checks.csv", file_checks())
    rows, examples = row_checks()
    write("compliance_row_checks.csv", rows)
    write("compliance_examples.csv", examples)


if __name__ == "__main__":
    main()
