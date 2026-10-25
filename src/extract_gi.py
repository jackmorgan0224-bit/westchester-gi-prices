"""Pull every GI endoscopy row (colonoscopy, EGD, EUS) out of the raw hospital files.

Hospitals publish their standard charges in one of three CMS layouts, and all three
appear in Westchester:
- CSV "tall": one row per item x payer x plan (payer_name / plan_name columns)
- CSV "wide": one row per item, one column group per payer x plan
  (standard_charge|<payer>|<plan>|negotiated_dollar, ...)
- JSON: standard_charge_information -> standard_charges -> payers_information

This script reads each file once (streaming the JSON, which runs to 600+ MB), keeps
rows billed under a target CPT/HCPCS code, and writes one long table with the same
columns for every hospital: data/gi_rows.csv. Values are copied as published; nothing
is filled in or estimated here.
"""

import argparse
import csv
import re
import zipfile
from pathlib import Path

import duckdb
import ijson

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
UNZIP_DIR = RAW_DIR / "_unzipped"
INTERIM_DIR = ROOT / "data" / "interim"
OUT = ROOT / "data" / "gi_rows.csv"
CODES = {r["code"] for r in csv.DictReader(open(ROOT / "data" / "reference" / "gi_codes.csv", encoding="utf-8"))}
CODE_TYPES = {"CPT", "HCPCS"}

FIELDS = [
    "hospital_id", "file_version", "file_last_updated", "description", "code", "code_type", "other_codes",
    "modifiers", "setting", "billing_class", "gross_charge", "discounted_cash", "min_negotiated", "max_negotiated",
    "payer_name", "plan_name", "negotiated_dollar", "negotiated_percentage", "negotiated_algorithm", "methodology",
    "median_amount", "p10_amount", "p90_amount", "allowed_count", "additional_payer_notes", "additional_generic_notes",
]

# CSV header -> our column, for the per-item (non-payer) fields shared by both CSV layouts
CSV_ITEM_COLS = {
    "description": "description", "modifiers": "modifiers", "setting": "setting", "billing_class": "billing_class",
    "standard_charge|gross": "gross_charge", "standard_charge|discounted_cash": "discounted_cash",
    "standard_charge|min": "min_negotiated", "standard_charge|max": "max_negotiated",
    "additional_generic_notes": "additional_generic_notes",
}
# Tall-CSV payer fields
CSV_PAYER_COLS = {
    "payer_name": "payer_name", "plan_name": "plan_name",
    "standard_charge|negotiated_dollar": "negotiated_dollar",
    "standard_charge|negotiated_percentage": "negotiated_percentage",
    "standard_charge|negotiated_algorithm": "negotiated_algorithm",
    "standard_charge|methodology": "methodology", "median_amount": "median_amount",
    "10th_percentile": "p10_amount", "90th_percentile": "p90_amount", "count": "allowed_count",
    "additional_payer_notes": "additional_payer_notes",
}
# Wide-CSV payer fields: the last segment of standard_charge|<payer>|<plan>|<field>,
# or the first segment of <field>|<payer>|<plan>
WIDE_SUFFIX = {
    "negotiated_dollar": "negotiated_dollar", "negotiated_percentage": "negotiated_percentage",
    "negotiated_algorithm": "negotiated_algorithm", "methodology": "methodology",
}
WIDE_PREFIX = {
    "median_amount": "median_amount", "10th_percentile": "p10_amount", "90th_percentile": "p90_amount",
    "count": "allowed_count", "additional_payer_notes": "additional_payer_notes",
}


def clean(v):
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def code_pairs(row, header):
    """Return [(code, type), ...] from code|1, code|1|type, code|2, ..."""
    pairs = []
    i = 1
    while f"code|{i}" in header:
        code, ctype = clean(row.get(f"code|{i}")), clean(row.get(f"code|{i}|type")).upper()
        if code:
            pairs.append((code.upper(), ctype))
        i += 1
    return pairs


def split_codes(pairs):
    """Pick the target code; keep the rest (e.g. revenue codes, CDM numbers) for reference."""
    hits = [(c, t) for c, t in pairs if c in CODES and t in CODE_TYPES]
    if not hits:
        return None
    code, ctype = hits[0]
    others = ";".join(f"{c}:{t}" for c, t in pairs if (c, t) != (code, ctype))
    return code, ctype, others


def csv_path(path):
    """DuckDB can't read inside a zip, so unpack zipped CSVs once."""
    if path.suffix != ".zip":
        return path
    UNZIP_DIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        name = z.namelist()[0]
        dest = UNZIP_DIR / f"{path.name.split('.')[0]}.csv"
        if not dest.exists():
            with z.open(name) as src, open(dest, "wb") as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
    return dest


def read_csv_file(hospital_id, path):
    path = csv_path(path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        meta_header = next(csv.reader([f.readline()]))
        meta_values = next(csv.reader([f.readline()]))
    meta = dict(zip([h.strip() for h in meta_header], meta_values))
    version, last_updated = clean(meta.get("version")), clean(meta.get("last_updated_on"))

    # Header is row 3. Filter in DuckDB on the code columns so we never load 400 MB into Python.
    con = duckdb.connect()
    rel = con.sql(f"""
        SELECT * FROM read_csv('{path.as_posix()}', skip=2, header=true, all_varchar=true,
                               quote='"', escape='"', strict_mode=false, null_padding=true)
    """)
    header = rel.columns
    code_cols = [c for c in header if re.fullmatch(r"code\|\d+", c)]
    where = " OR ".join(f"upper(trim(\"{c}\")) IN ({','.join(repr(x) for x in CODES)})" for c in code_cols)
    df = con.sql(f"SELECT * FROM rel WHERE {where}").df()
    header = list(df.columns)
    tall = "payer_name" in header

    wide_groups = {}
    if not tall:
        for col in header:
            parts = col.split("|")
            if parts[0] == "standard_charge" and len(parts) == 4 and parts[3] in WIDE_SUFFIX:
                wide_groups.setdefault((parts[1], parts[2]), {})[WIDE_SUFFIX[parts[3]]] = col
            elif parts[0] in WIDE_PREFIX and len(parts) == 3:
                wide_groups.setdefault((parts[1], parts[2]), {})[WIDE_PREFIX[parts[0]]] = col

    rows = []
    for rec in df.to_dict("records"):
        rec = {k: (None if v != v else v) for k, v in rec.items()}  # NaN -> None
        picked = split_codes(code_pairs(rec, header))
        if not picked:
            continue
        base = {f: "" for f in FIELDS}
        base.update(hospital_id=hospital_id, file_version=version, file_last_updated=last_updated,
                    code=picked[0], code_type=picked[1], other_codes=picked[2])
        for src, dst in CSV_ITEM_COLS.items():
            base[dst] = clean(rec.get(src))
        if tall:
            out = dict(base)
            for src, dst in CSV_PAYER_COLS.items():
                out[dst] = clean(rec.get(src))
            rows.append(out)
        else:
            # One output row per item even when no payer has a rate (keeps gross/cash-only items)
            emitted = False
            for (payer, plan), cols in wide_groups.items():
                vals = {dst: clean(rec.get(src)) for dst, src in cols.items()}
                if not any(vals.get(k) for k in ("negotiated_dollar", "negotiated_percentage", "negotiated_algorithm")):
                    continue
                out = dict(base, payer_name=payer, plan_name=plan, **vals)
                rows.append(out)
                emitted = True
            if not emitted:
                rows.append(base)
    return rows


def open_json(path):
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        f = z.open(z.namelist()[0])
    else:
        f = open(path, "rb")
    # Northwell's files start with a UTF-8 byte order mark, which the JSON parser rejects
    if f.peek(3)[:3] == b"\xef\xbb\xbf":
        f.read(3)
    return f


def json_header(path):
    """Read the top-level metadata that precedes standard_charge_information."""
    meta = {}
    with open_json(path) as f:
        for prefix, event, value in ijson.parse(f):
            if prefix == "standard_charge_information":
                break
            if prefix in ("version", "last_updated_on"):
                meta[prefix] = value
    return meta


def read_json_file(hospital_id, path):
    meta = json_header(path)
    version, last_updated = clean(meta.get("version")), clean(meta.get("last_updated_on"))
    rows = []
    with open_json(path) as f:
        for item in ijson.items(f, "standard_charge_information.item", use_float=True):
            pairs = [(clean(c.get("code")).upper(), clean(c.get("type")).upper()) for c in item.get("code_information", [])]
            picked = split_codes(pairs)
            if not picked:
                continue
            for sc in item.get("standard_charges", []):
                base = {f: "" for f in FIELDS}
                base.update(
                    hospital_id=hospital_id, file_version=version, file_last_updated=last_updated,
                    description=clean(item.get("description")), code=picked[0], code_type=picked[1],
                    other_codes=picked[2], modifiers=clean("|".join(sc.get("modifier_code", []) or [])),
                    setting=clean(sc.get("setting")), billing_class=clean(sc.get("billing_class")),
                    gross_charge=clean(sc.get("gross_charge")), discounted_cash=clean(sc.get("discounted_cash")),
                    min_negotiated=clean(sc.get("minimum")), max_negotiated=clean(sc.get("maximum")),
                    additional_generic_notes=clean(sc.get("additional_generic_notes")),
                )
                payers = sc.get("payers_information") or []
                if not payers:
                    rows.append(base)
                for p in payers:
                    rows.append(dict(
                        base,
                        payer_name=clean(p.get("payer_name")), plan_name=clean(p.get("plan_name")),
                        negotiated_dollar=clean(p.get("standard_charge_dollar")),
                        negotiated_percentage=clean(p.get("standard_charge_percentage")),
                        negotiated_algorithm=clean(p.get("standard_charge_algorithm")),
                        methodology=clean(p.get("methodology")),
                        median_amount=clean(p.get("median_amount")), p10_amount=clean(p.get("10th_percentile")),
                        p90_amount=clean(p.get("90th_percentile")), allowed_count=clean(p.get("count")),
                        additional_payer_notes=clean(p.get("additional_payer_notes")),
                    ))
    return rows


def is_json_file(path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            return z.namelist()[0].lower().endswith(".json")
    return path.suffix == ".json"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-extract hospitals already cached in data/interim/")
    args = parser.parse_args()
    INTERIM_DIR.mkdir(exist_ok=True)
    manifest = list(csv.DictReader(open(RAW_DIR / "manifest.csv", encoding="utf-8")))
    all_rows = []
    for m in manifest:
        path, cache = RAW_DIR / m["file"], INTERIM_DIR / f"{m['hospital_id']}.csv"
        if cache.exists() and not args.force:
            rows = list(csv.DictReader(open(cache, encoding="utf-8")))
            print(f"{m['hospital_id']:8s} cached {len(rows):6d} GI rows")
        else:
            is_json = is_json_file(path)
            rows = read_json_file(m["hospital_id"], path) if is_json else read_csv_file(m["hospital_id"], path)
            with open(cache, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader()
                w.writerows(rows)
            print(f"{m['hospital_id']:8s} {'json' if is_json else 'csv ':4s} {len(rows):6d} GI rows")
        all_rows.extend(rows)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(all_rows)} rows)")


if __name__ == "__main__":
    main()
