"""Independent checks on the pipeline.

The re-derivation tests read the raw hospital files with a different code path than
src/extract_gi.py (pandas for CSV, a hand-rolled ijson filter for JSON) and confirm the
numbers in data/gi_prices.duckdb match, one test per CMS file layout. They skip when the
raw files have not been downloaded (run src/fetch_mrfs.py first).
"""

import sys
import zipfile
from pathlib import Path

import duckdb
import ijson
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "gi_prices.duckdb"
sys.path.insert(0, str(ROOT / "src"))

from classify_payers import classify  # noqa: E402

needs_raw = pytest.mark.skipif(not (RAW / "manifest.csv").exists() or not DB.exists(),
                               reason="raw files / database not built")


def db_rate(hospital, code, payer, plan):
    con = duckdb.connect(str(DB), read_only=True)
    row = con.execute("""SELECT negotiated_dollar, price_basis FROM negotiated
                         WHERE hospital_id = ? AND code = ? AND payer_name = ? AND plan_name = ?""",
                      [hospital, code, payer, plan]).fetchone()
    con.close()
    return row


def csv_rows_for_code(path, code):
    """All rows of a CMS CSV (header on row 3) where any code|i column equals `code`."""
    hits = []
    for chunk in pd.read_csv(path, skiprows=2, dtype=str, chunksize=50_000, keep_default_na=False):
        code_cols = [c for c in chunk.columns if c.startswith("code|") and not c.endswith("|type")]
        mask = chunk[code_cols].apply(lambda s: s.str.strip().str.upper() == code).any(axis=1)
        hits.append(chunk[mask])
    return pd.concat(hits)


@needs_raw
def test_wide_csv_westchester_medical_center():
    rows = csv_rows_for_code(RAW / "wmc.csv", "45378")
    rows = rows[rows["setting"].str.lower() == "outpatient"]
    case = rows[rows["standard_charge|Aetna|Aetna|methodology"].str.lower() == "case rate"]
    expected = float(case["standard_charge|Aetna|Aetna|negotiated_dollar"].iloc[0])
    got, basis = db_rate("wmc", "45378", "Aetna", "Aetna")
    assert basis == "case rate"
    assert got == pytest.approx(expected)


@needs_raw
def test_tall_csv_white_plains():
    rows = csv_rows_for_code(RAW / "wph.csv", "45378")
    rows = rows[(rows["payer_name"] == "UHC") & (rows["plan_name"] == "Oxford")
                & (rows["standard_charge|methodology"].str.lower() == "case rate")]
    values = rows["standard_charge|negotiated_dollar"].astype(float)
    got, basis = db_rate("wph", "45378", "UHC", "Oxford")
    assert basis == "case rate"
    assert got == pytest.approx(values.median())


@needs_raw
def test_json_nyp_hudson_valley():
    with zipfile.ZipFile(RAW / "nyp_hv.json.zip") as z, z.open(z.namelist()[0]) as f:
        expected = None
        for item in ijson.items(f, "standard_charge_information.item", use_float=True):
            if not any(c.get("code") == "45378" and c.get("type") == "CPT" for c in item["code_information"]):
                continue
            for sc in item["standard_charges"]:
                for p in sc.get("payers_information", []):
                    if p["payer_name"] == "Aetna" and p["plan_name"] == "Commercial":
                        expected = p["standard_charge_dollar"]
            break
    got, _ = db_rate("nyp_hv", "45378", "Aetna", "Commercial")
    assert expected is not None
    assert got == pytest.approx(expected)


@pytest.mark.parametrize("hospital, payer, plan, family, segment", [
    ("nwh", "Oxford", "Oxford Medicare", "UnitedHealthcare", "Medicare Advantage"),
    ("wmc", "UHC EMPIRE", "UHC EMPIRE", "UnitedHealthcare", "Commercial"),
    ("nwh", "HealthPlus", "HealthPlus (FHP) Medicaid", "Anthem / Empire BCBS", "Medicaid managed care"),
    ("wmc", "BLUE CROSS CONNECTION/EXCHANGE", "BLUE CROSS CONNECTION/EXCHANGE", "Anthem / Empire BCBS", "Exchange (individual/small group)"),
    ("wph", "Fidelis", "Essential Plan - Aliessa", "Fidelis", "Essential Plan"),
    ("mmv", "Multiplan", "Multiplan", "Rental network", "Rental network"),
    ("phelps", "Emblem", "GHI Medicare", "EmblemHealth", "Medicare Advantage"),
    ("sjr", "Carelon Medicaid", "Carelon Medicaid", "Other", "Behavioral carve-out"),
    # Names the independent audit found misclassified in an earlier version
    ("sjr", "Empire Blue Cross Blue Shield", "Individual Network", "Anthem / Empire BCBS", "Exchange (individual/small group)"),
    ("sjr", "MVP Individual Exchange.Student Health Plan", "MVP Individual Exchange.Student Health Plan", "MVP", "Exchange (individual/small group)"),
    ("sjmc", "Healthfirst QHP", "Medicaid Managed Care", "Healthfirst", "Exchange (individual/small group)"),
    ("mmv", "MetroPlus", "HIV_SNP", "MetroPlus", "Medicaid managed care"),
    ("mnr", "MetroPlus", "HIV SNP", "MetroPlus", "Medicaid managed care"),
    ("mmv", "MetroPlus", "Default Duals", "MetroPlus", "Medicare Advantage"),
])
def test_payer_classification(hospital, payer, plan, family, segment):
    got = classify(hospital, payer, plan)
    assert (got["payer_family"], got["segment"]) == (family, segment)
