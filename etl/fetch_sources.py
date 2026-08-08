#!/usr/bin/env python3
"""Download the public-domain source datasets once, into data/sources/.

Nothing in the running app touches the network -- this is setup-time only.
Re-running skips files that are already present (pass --force to refetch).

Sources
  KJV / ASV / BSB  scrollmapper/bible_databases (JSON, one file per translation)
  WEB              seven1m/open-bibles (USFX XML; scrollmapper has no WEB)
  Nave's Topical   BradyStephenson/bible-data (CSV, CC BY 4.0)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "sources"

SCROLLMAPPER = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json"

DOWNLOADS = [
    ("KJV.json", f"{SCROLLMAPPER}/KJV.json"),
    ("ASV.json", f"{SCROLLMAPPER}/ASV.json"),
    ("BSB.json", f"{SCROLLMAPPER}/BSB.json"),
    (
        "eng-web.usfx.xml",
        "https://raw.githubusercontent.com/seven1m/open-bibles/master/eng-web.usfx.xml",
    ),
    (
        "NavesTopicalDictionary.csv",
        "https://raw.githubusercontent.com/BradyStephenson/bible-data/main/NavesTopicalDictionary.csv",
    ),
]


def download(name: str, url: str, force: bool) -> Path:
    dest = SOURCES_DIR / name
    if dest.exists() and not force:
        print(f"  have  {name} ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  fetch {name} <- {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 16):
            fh.write(chunk)
    tmp.replace(dest)
    print(f"        {dest.stat().st_size:,} bytes")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="refetch files already on disk")
    args = ap.parse_args()

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"sources -> {SOURCES_DIR}")
    for name, url in DOWNLOADS:
        try:
            download(name, url, args.force)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  FAIL  {name}: {exc}", file=sys.stderr)
            return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
