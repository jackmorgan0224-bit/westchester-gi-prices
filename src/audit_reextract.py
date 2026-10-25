"""Audit: re-extract every GI row a second way and compare field by field to data/gi_rows.csv.

Written separately from src/extract_gi.py and shares no code with it: pandas chunked reads
for every CSV (no DuckDB) and its own JSON walk. Each row becomes a 16-field signature
(hospital, code, description, setting, payer, plan, methodology, dollar, percentage,
algorithm, gross, cash, min, max, median, count) and the two sets are compared as
multisets, so a missing, extra, or altered row on either side shows up as a mismatch.

Usage: python src/audit_reextract.py   (about 10 minutes; needs data/raw from fetch_mrfs.py)
"""
import csv
import sys
import zipfile
from collections import Counter
from pathlib import Path

import ijson
import pandas as pd

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CODES = set(pd.read_csv(ROOT / "data/reference/gi_codes.csv", dtype=str)["code"])


def num(v):
    v = "" if v is None else str(v).strip().replace(",", "")
    if v == "" or v.lower() == "nan":
        return ""
    try:
        return f"{float(v):.2f}"
    except ValueError:
        return v


def txt(v):
    v = "" if v is None else str(v)
    return " ".join(v.split()) if v.lower() != "nan" else ""


def sig(h, code, desc, setting, payer, plan, method, dollar, pct, alg, gross, cash, mn, mx, med, cnt):
    return (h, code, txt(desc).upper(), txt(setting).lower(), txt(payer), txt(plan), txt(method).lower(),
            num(dollar), num(pct), txt(alg)[:60], num(gross), num(cash), num(mn), num(mx), num(med), txt(cnt))


def first_code(row, code_cols):
    for c in code_cols:
        v = str(row.get(c, "")).strip().upper()
        t = str(row.get(c + "|type", "")).strip().upper()
        if v in CODES and t in ("CPT", "HCPCS"):
            return v
    return None


def open_csv(path):
    if path.suffix == ".zip":
        z = zipfile.ZipFile(path)
        return z.open(z.namelist()[0])
    return open(path, "rb")


def csv_rows(h, path):
    out = []
    with open_csv(path) as f:
        reader = pd.read_csv(f, skiprows=2, dtype=str, keep_default_na=False, chunksize=40000,
                             encoding="utf-8-sig", low_memory=False)
        for chunk in reader:
            code_cols = [c for c in chunk.columns if c.startswith("code|") and c.count("|") == 1]
            mask = pd.Series(False, index=chunk.index)
            for c in code_cols:
                mask |= chunk[c].str.strip().str.upper().isin(CODES)
            sub = chunk[mask]
            tall = "payer_name" in chunk.columns
            for _, r in sub.iterrows():
                code = first_code(r, code_cols)
                if not code:
                    continue
                base = (r.get("description"), r.get("setting"))
                item = dict(gross=r.get("standard_charge|gross"), cash=r.get("standard_charge|discounted_cash"),
                            mn=r.get("standard_charge|min"), mx=r.get("standard_charge|max"))
                if tall:
                    out.append(sig(h, code, *base, r.get("payer_name"), r.get("plan_name"),
                                   r.get("standard_charge|methodology"), r.get("standard_charge|negotiated_dollar"),
                                   r.get("standard_charge|negotiated_percentage"), r.get("standard_charge|negotiated_algorithm"),
                                   item["gross"], item["cash"], item["mn"], item["mx"], r.get("median_amount"), r.get("count")))
                else:
                    groups = {}
                    for col in chunk.columns:
                        p = col.split("|")
                        if p[0] == "standard_charge" and len(p) == 4:
                            groups.setdefault((p[1], p[2]), {})[p[3]] = r[col]
                        elif p[0] in ("median_amount", "count") and len(p) == 3:
                            groups.setdefault((p[1], p[2]), {})[p[0]] = r[col]
                    emitted = False
                    for (payer, plan), g in groups.items():
                        if not any(str(g.get(k, "")).strip() for k in ("negotiated_dollar", "negotiated_percentage", "negotiated_algorithm")):
                            continue
                        out.append(sig(h, code, *base, payer, plan, g.get("methodology"), g.get("negotiated_dollar"),
                                       g.get("negotiated_percentage"), g.get("negotiated_algorithm"),
                                       item["gross"], item["cash"], item["mn"], item["mx"], g.get("median_amount"), g.get("count")))
                        emitted = True
                    if not emitted:
                        out.append(sig(h, code, *base, "", "", "", "", "", "", item["gross"], item["cash"], item["mn"], item["mx"], "", ""))
    return out


def json_rows(h, path):
    out = []
    z = zipfile.ZipFile(path) if path.suffix == ".zip" else None
    f = z.open(z.namelist()[0]) if z else open(path, "rb")
    head = f.read(3)
    if head != b"\xef\xbb\xbf":
        # re-open to start from byte 0
        f.close()
        f = z.open(z.namelist()[0]) if z else open(path, "rb")
    for item in ijson.items(f, "standard_charge_information.item", use_float=True):
        code = None
        for ci in item.get("code_information", []):
            c, t = str(ci.get("code", "")).strip().upper(), str(ci.get("type", "")).strip().upper()
            if c in CODES and t in ("CPT", "HCPCS"):
                code = c
                break
        if not code:
            continue
        for sc in item.get("standard_charges", []):
            pis = sc.get("payers_information") or [{}]
            for p in pis:
                out.append(sig(h, code, item.get("description"), sc.get("setting"), p.get("payer_name"), p.get("plan_name"),
                               p.get("methodology"), p.get("standard_charge_dollar"), p.get("standard_charge_percentage"),
                               p.get("standard_charge_algorithm"), sc.get("gross_charge"), sc.get("discounted_cash"),
                               sc.get("minimum"), sc.get("maximum"), p.get("median_amount"), p.get("count")))
    f.close()
    return out


def pipeline_rows():
    out = []
    with open(ROOT / "data/gi_rows.csv", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.append(sig(r["hospital_id"], r["code"], r["description"], r["setting"], r["payer_name"], r["plan_name"],
                           r["methodology"], r["negotiated_dollar"], r["negotiated_percentage"], r["negotiated_algorithm"],
                           r["gross_charge"], r["discounted_cash"], r["min_negotiated"], r["max_negotiated"],
                           r["median_amount"], r["allowed_count"]))
    return out


def main():
    manifest = list(csv.DictReader(open(RAW / "manifest.csv", encoding="utf-8")))
    indep = []
    for m in manifest:
        p = RAW / m["file"]
        is_json = p.suffix == ".json" or (p.suffix == ".zip" and zipfile.ZipFile(p).namelist()[0].lower().endswith(".json"))
        rows = json_rows(m["hospital_id"], p) if is_json else csv_rows(m["hospital_id"], p)
        print(m["hospital_id"], len(rows), flush=True)
        indep.extend(rows)
    pipe = pipeline_rows()
    a, b = Counter(indep), Counter(pipe)
    only_indep, only_pipe = a - b, b - a
    print("independent rows:", len(indep), "pipeline rows:", len(pipe))
    print("rows only in independent:", sum(only_indep.values()), " rows only in pipeline:", sum(only_pipe.values()))
    by_h = Counter(k[0] for k in only_indep.elements())
    print("mismatch by hospital (independent side):", dict(by_h))
    for k in list(only_indep)[:8]:
        print("IND ", k)
    for k in list(only_pipe)[:8]:
        print("PIPE", k)


if __name__ == "__main__":
    main()
