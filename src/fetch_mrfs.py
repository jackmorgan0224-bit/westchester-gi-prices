"""Download each Westchester hospital's machine-readable standard charges file (MRF).

Hospitals must post a cms-hpt.txt index at the root of their website that names each
location and the URL of its MRF (45 CFR 180.50(d)(6)). This script reads that index
for every hospital in data/reference/hospitals.csv, follows the mrf-url, and caches
the file in data/raw/. It also writes data/raw/manifest.csv recording what the index
said, the HTTP response, and a SHA-256 of each file, so later steps (and the
compliance checks) know exactly which version was analyzed.

Files that already exist are skipped; pass --force to re-download.
"""

import argparse
import csv
import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
HOSPITALS_CSV = ROOT / "data" / "reference" / "hospitals.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (westchester-gi-prices; personal research project)"}
TIMEOUT = 120
CHUNK = 1 << 20


def parse_index(text):
    """Split a cms-hpt.txt file into one dict per location-name block."""
    entries, current = [], {}
    for line in re.split(r"\r\n|\r|\n", text):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip().lower(), value.strip()
        if key == "location-name" and current:
            entries.append(current)
            current = {}
        current[key] = value
    if current:
        entries.append(current)
    return entries


def file_name(hospital_id, url, content_type):
    path = urlparse(url).path.lower()
    for ext in (".json.zip", ".csv.zip", ".zip", ".json", ".csv"):
        if path.endswith(ext):
            return f"{hospital_id}{ext}"
    # Vendor APIs (e.g. Craneware) serve the file without an extension
    return f"{hospital_id}.json" if "json" in (content_type or "") else f"{hospital_id}.csv"


def download(url, dest):
    sha = hashlib.sha256()
    with requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
                sha.update(chunk)
        tmp.replace(dest)
        return r.headers.get("Last-Modified", ""), r.headers.get("Content-Type", ""), sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = parser.parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with open(HOSPITALS_CSV, newline="", encoding="utf-8") as f:
        hospitals = list(csv.DictReader(f))

    manifest_path = RAW_DIR / "manifest.csv"
    previous = {}
    if manifest_path.exists():
        with open(manifest_path, newline="", encoding="utf-8") as f:
            previous = {row["hospital_id"]: row for row in csv.DictReader(f)}

    indexes, rows = {}, []
    for h in hospitals:
        if h["index_url"] not in indexes:
            r = requests.get(h["index_url"], headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            indexes[h["index_url"]] = parse_index(r.text)
            time.sleep(1)
        matches = [e for e in indexes[h["index_url"]] if e.get("location-name") == h["location_name"]]
        if len(matches) != 1:
            raise SystemExit(f"{h['hospital_id']}: expected 1 index entry for {h['location_name']!r}, found {len(matches)}")
        entry = matches[0]
        url = entry["mrf-url"]

        # Several locations can share one system-wide file; download it once
        shared = next((row for row in rows if row["mrf_url"] == url), None)
        if shared:
            row = dict(shared, hospital_id=h["hospital_id"])
        else:
            head = requests.head(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            dest = RAW_DIR / file_name(h["hospital_id"], url, head.headers.get("Content-Type"))
            if dest.exists() and not args.force and h["hospital_id"] in previous:
                print(f"skip {dest.name} (cached)")
                row = previous[h["hospital_id"]]
            else:
                print(f"download {h['hospital_id']} <- {url}")
                last_modified, content_type, sha = download(url, dest)
                # Some vendor APIs serve a zip with no extension or zip content type
                with open(dest, "rb") as f:
                    if f.read(2) == b"PK" and dest.suffix != ".zip":
                        dest = dest.replace(dest.with_name(dest.name + ".zip"))
                row = {
                    "hospital_id": h["hospital_id"],
                    "mrf_url": url,
                    "file": dest.name,
                    "bytes": dest.stat().st_size,
                    "http_last_modified": last_modified,
                    "content_type": content_type,
                    "sha256": sha,
                    "downloaded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
                time.sleep(1)
        row["index_url"] = h["index_url"]
        row["index_source_page_url"] = entry.get("source-page-url", "")
        row["index_contact_listed"] = "yes" if entry.get("contact-name") and entry.get("contact-email") else "no"
        rows.append(row)

    fields = ["hospital_id", "mrf_url", "file", "bytes", "http_last_modified", "content_type", "sha256",
              "downloaded_utc", "index_url", "index_source_page_url", "index_contact_listed"]
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: row.get(k, "") for k in fields} for row in rows)
    print(f"wrote {manifest_path.relative_to(ROOT)} ({len(rows)} hospitals)")


if __name__ == "__main__":
    main()
