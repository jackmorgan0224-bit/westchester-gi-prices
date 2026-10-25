"""Map every payer/plan name in the hospital files to a payer family and a market segment.

Each hospital spells payers its own way ("UHC || Oxford", "Oxford || Oxford PPO",
"United Healthcare || Oxford OX"). Comparing insurers across hospitals needs two
labels:
- payer_family: the parent insurer (Oxford rolls up to UnitedHealthcare, HealthPlus
  to Anthem/Empire BCBS, GHI and HIP to EmblemHealth)
- segment: the line of business, because the same insurer pays very different rates
  for commercial, Medicare Advantage, and Medicaid members

Rules are ordered and the first match wins. Output: data/reference/payer_map.csv, one row
per hospital x payer x plan, with the rule that fired so every label can be audited.
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (family, regex on "payer || plan", lowercased). Order matters: Oxford and Empire Plan
# before the generic United/Empire patterns, HealthPlus before generic Anthem.
FAMILY_RULES = [
    ("UnitedHealthcare", r"oxford|\buhc\b|united(?! behavioral)|uhc empire"),
    ("Anthem / Empire BCBS", r"anthem|empire|healthplus|blue cross"),
    ("Aetna", r"aetna"),
    ("Cigna", r"cigna"),
    ("EmblemHealth", r"emblem|\bghi\b|\bhip\b|connecticare"),
    ("Fidelis", r"fidelis"),
    ("Healthfirst", r"healthfirst"),
    ("MVP", r"\bmvp\b|mohawk"),
    ("MetroPlus", r"metroplus"),
    ("Molina / Affinity", r"molina|affinity"),
    ("Wellcare", r"wellcare"),
    ("VNS Health", r"\bvns"),
    ("Oscar", r"oscar"),
    ("Humana", r"humana"),
    ("CDPHP", r"cdphp"),
    ("1199SEIU", r"1199"),
    ("Traditional Medicare", r"^medicare \|\| medicare$|medigap"),
    ("Self-pay", r"self-pay"),
    ("Northwell Direct", r"northwell"),
]

# Rental (leased) networks: the employer or TPA rents the hospital's discount; no insurer risk
RENTAL = r"multiplan|claritev|\bphcs\b|magna|first health|beech street|consumer health network|devon|point comfort|worldwide|\bqhm\b|consolidated health|emblem leased"
BEHAVIORAL = r"beacon|value options|carelon|behavioral|\bbhs\b"
GOVERNMENT_OTHER = r"tricare|veteran|^va \|\||community care"

SEGMENT_RULES = [
    ("Self-pay", r"self-pay"),
    ("Out-of-network", r"non contracted"),
    ("Behavioral carve-out", BEHAVIORAL),
    ("Government (VA/Tricare)", GOVERNMENT_OTHER),
    ("Traditional Medicare", r"^medicare \|\| medicare$|medigap"),
    ("Rental network", RENTAL),
    ("Essential Plan", r"essential|aliessa|allessa"),
    ("Medicaid managed care", r"medicaid advantage|\bpace\b|\bfida\b|dually enrolled|harp|child health|\bchp\b|\bchip\b|medicaid|\bmcd\b|\bfhp\b|hiv primary care|vnsny select|partners health"),
    ("Medicare Advantage", r"medicare|\bmcr\b|snp|dual|elderplan|longevity|hamaspik|centerlight|villagecare|village caremax|vns choice|vnsny choice|centers plan|senior whole health|humana|^wellcare \|\| wellcare$"),
    ("Exchange (individual/small group)", r"exchange|\bqhp\b|nystateofhealth|individual|select care|student health"),
]


def classify(hospital_id, payer, plan):
    text = f"{payer} || {plan}".lower().replace("&amp;", "&")
    family = next((f for f, rx in FAMILY_RULES if re.search(rx, text)), "Other")
    seg_rule = next(((s, rx) for s, rx in SEGMENT_RULES if re.search(rx, text)), ("Commercial", "default"))
    segment = seg_rule[0]
    if segment == "Rental network":
        family = "Rental network"
    return {"hospital_id": hospital_id, "payer_name": payer, "plan_name": plan,
            "payer_family": family, "segment": segment, "segment_rule": seg_rule[1]}


def main():
    seen = {}
    with open(ROOT / "data" / "gi_rows.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["payer_name"] or r["plan_name"]:
                key = (r["hospital_id"], r["payer_name"], r["plan_name"])
                seen.setdefault(key, classify(*key))
    rows = sorted(seen.values(), key=lambda r: (r["hospital_id"], r["payer_name"], r["plan_name"]))
    out = ROOT / "data" / "reference" / "payer_map.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out.relative_to(ROOT)} ({len(rows)} payer/plan names)")


if __name__ == "__main__":
    main()
