"""Build the Medicare benchmark: what traditional Medicare pays each Westchester hospital
for the facility side of each GI procedure in 2026.

Hospital outpatient procedures are paid under the Outpatient Prospective Payment System
(OPPS). Each CPT/HCPCS code maps to an APC with a national payment rate (Addendum B).
CMS then adjusts 60% of that rate (the labor share) by the hospital's wage index:

    adjusted rate = national rate x (0.60 x wage index + 0.40)

Inputs (downloaded once into data/reference/cms_dl/):
- October 2026 OPPS Addendum B (national rates by HCPCS)
- FY 2026 IPPS final rule Table 2 (wage index by hospital CCN; OPPS uses the IPPS index)

Output: data/reference/medicare_opps_2026.csv. CPT descriptors are AMA-copyrighted, so
the output carries our own plain-English labels from gi_codes.csv instead.
"""

import csv
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
DL = REF / "cms_dl"
ADDENDUM_B_URL = "https://www.cms.gov/files/zip/October-2026-OPPS-Addendum-B.zip"
TABLE_2_URL = "https://www.cms.gov/files/zip/fy2026-ipps-fr-tables-2-3-4a-4b.zip"
LABOR_SHARE = 0.60
HEADERS = {"User-Agent": "Mozilla/5.0 (westchester-gi-prices; personal research project)"}

# CMS Certification Numbers (Care Compare). NYP Westchester bills under NewYork-Presbyterian's CCN.
CCN = {
    "wmc": "330234", "nyp_hv": "330267", "nyp_wch": "330101", "nwh": "330162", "phelps": "330261",
    "wph": "330304", "mmv": "330086", "mnr": "330184", "sjr": "330208", "sjmc": "330006",
}


def fetch(url, dest):
    if not dest.exists():
        DL.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return zipfile.ZipFile(dest)


def addendum_b():
    z = fetch(ADDENDUM_B_URL, DL / "addb.zip")
    name = next(n for n in z.namelist() if n.endswith(".xlsx"))
    raw = pd.read_excel(io.BytesIO(z.read(name)), header=None, dtype=str)
    header_row = raw.index[raw.iloc[:, 0].fillna("").str.strip() == "HCPCS Code"][0]
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header_row]]
    df["HCPCS Code"] = df["HCPCS Code"].str.strip()
    return df.set_index("HCPCS Code")


def wage_index():
    z = fetch(TABLE_2_URL, DL / "ipps_t2.zip")
    name = next(n for n in z.namelist() if n.endswith("Tables 2.txt"))
    df = pd.read_csv(io.StringIO(z.read(name).decode("latin1")), sep="\t", dtype=str, skiprows=1)
    df.columns = [c.strip() for c in df.columns]
    ccn_col = df.columns[0]
    wi_col = next(c for c in df.columns if "FY 2026 Wage Index With Cap" in c)
    return dict(zip(df[ccn_col].str.strip(), df[wi_col].astype(float)))


def main():
    codes = list(csv.DictReader(open(REF / "gi_codes.csv", encoding="utf-8")))
    rates, wi = addendum_b(), wage_index()
    hospital_wi = {h: wi[c] for h, c in CCN.items()}
    if len(set(hospital_wi.values())) != 1:
        print("note: wage index differs across hospitals:", hospital_wi)

    rows = []
    for c in codes:
        r = rates.loc[c["code"]]
        national = float(r["Payment Rate"])
        for h, w in hospital_wi.items():
            rows.append({
                "hospital_id": h, "ccn": CCN[h], "code": c["code"], "family": c["family"], "label": c["label"],
                "status_indicator": r["SI"].strip(), "apc": r["APC"].strip(), "national_rate": national,
                "wage_index": w, "medicare_rate": round(national * (LABOR_SHARE * w + 1 - LABOR_SHARE), 2),
            })
    out = REF / "medicare_opps_2026.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
