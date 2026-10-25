"""Build data/gi_prices.duckdb from the extracted rows and run the validation checks.

Runs sql/01_build.sql, then every check in sql/02_validation.sql. Writes the check
results to results/validation.csv and exits non-zero if any check fails, so nothing
downstream (compliance, analysis, figures) runs on a bad build.
"""

import csv
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def main():
    con = duckdb.connect(str(ROOT / "data" / "gi_prices.duckdb"))
    con.execute(f"SET file_search_path = '{ROOT.as_posix()}'")
    con.execute((ROOT / "sql" / "01_build.sql").read_text())

    checks = []
    for stmt in (ROOT / "sql" / "02_validation.sql").read_text().split(";"):
        body = "\n".join(line for line in stmt.splitlines() if not line.strip().startswith("--")).strip()
        if body:
            checks.append(con.sql(body).fetchone())

    (ROOT / "results").mkdir(exist_ok=True)
    with open(ROOT / "results" / "validation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check", "status", "detail"])
        w.writerows(checks)
    for name, status, detail in checks:
        print(f"[{status}] {name}: {detail}")
    failed = [c for c in checks if c[1] != "PASS"]
    if failed:
        sys.exit(f"{len(failed)} validation check(s) failed; build stopped")
    print(f"all {len(checks)} checks pass")


if __name__ == "__main__":
    main()
