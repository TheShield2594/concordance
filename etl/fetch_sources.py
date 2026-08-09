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
import hashlib
import sys
import urllib.request
from pathlib import Path

SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "sources"

# URLs are pinned to commits, not branch heads, so a rebuild years from now
# produces the same database. Each file is checked against its digest before it
# is allowed into data/sources -- if upstream ever serves something else, the
# fetch fails loudly instead of quietly changing the text of scripture.
SCROLLMAPPER = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/"
    "e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c/formats/json"
)
OPEN_BIBLES = (
    "https://raw.githubusercontent.com/seven1m/open-bibles/"
    "f257a3559025c3f873b48a75019f53a9354ed7de"
)
BIBLE_DATA = (
    "https://raw.githubusercontent.com/BradyStephenson/bible-data/"
    "c6bf7893c78352effad1c32dcc4dc2c0ffbb4ee1"
)

DOWNLOADS = [
    (
        "KJV.json",
        f"{SCROLLMAPPER}/KJV.json",
        "f0b09dc49dfb97bb84f03aae1fbf026485048c3cab31a7a41017e2d86ac1d11c",
    ),
    (
        "ASV.json",
        f"{SCROLLMAPPER}/ASV.json",
        "602445e22c280a682ac4c489117ead179271f5ee50a78ee4531b249c71e7ce99",
    ),
    (
        "BSB.json",
        f"{SCROLLMAPPER}/BSB.json",
        "cec3c644088a8ef4a50cf1e2de035f79d8825f394625d116bb7ee7e1d57739c9",
    ),
    (
        "eng-web.usfx.xml",
        f"{OPEN_BIBLES}/eng-web.usfx.xml",
        "5ffa2626f170a109a4a96afc90775c06f0821cb4ba81ed34e63663e085708d68",
    ),
    (
        "NavesTopicalDictionary.csv",
        f"{BIBLE_DATA}/NavesTopicalDictionary.csv",
        "84f54e0c90293ed0674589cb417fa11a7dab572716735e5d626cc58645f1d49b",
    ),
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def download(name: str, url: str, expected: str, force: bool) -> Path:
    dest = SOURCES_DIR / name
    if dest.exists() and not force:
        if digest(dest) != expected:
            raise ValueError(
                f"{name} on disk does not match its expected digest; "
                "delete it and refetch"
            )
        print(f"  have  {name} ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  fetch {name} <- {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
        while chunk := resp.read(1 << 16):
            fh.write(chunk)
    got = digest(tmp)
    if got != expected:
        tmp.unlink()
        raise ValueError(f"{name} digest mismatch\n  expected {expected}\n  got      {got}")
    tmp.replace(dest)
    print(f"        {dest.stat().st_size:,} bytes, sha256 ok")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="refetch files already on disk")
    args = ap.parse_args()

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"sources -> {SOURCES_DIR}")
    failed = []
    for name, url, expected in DOWNLOADS:
        try:
            download(name, url, expected, args.force)
        except Exception as exc:  # noqa: BLE001 - report every failure, not the first
            print(f"  FAIL  {name}: {exc}", file=sys.stderr)
            failed.append(name)
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
