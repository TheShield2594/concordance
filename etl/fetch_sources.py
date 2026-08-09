#!/usr/bin/env python3
"""Download the public-domain source datasets once, into data/sources/.

Nothing in the running app touches the network -- this is setup-time only.
Re-running skips files that are already present (pass --force to refetch).

Sources
  KJV / ASV / BSB  scrollmapper/bible_databases (JSON, one file per translation)
  WEB              seven1m/open-bibles (USFX XML; scrollmapper has no WEB)
  Nave's Topical   BradyStephenson/bible-data (CSV, CC BY 4.0)
  TAHOT / TAGNT    STEPBible-Data: the Hebrew, Aramaic and Greek word by word,
                   tagged with Strong's numbers and morphology (CC BY 4.0)
  TEHMC / TEGMC    STEPBible-Data: those morphology codes in English
  Strong's         openscriptures/strongs: the dictionary entries themselves
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
STEPBIBLE = (
    "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/"
    "b86d26cdb1f51729e73b5b4eb7f7ccadc5dfba39"
)
STRONGS = (
    "https://raw.githubusercontent.com/openscriptures/strongs/"
    "0acd2f251c2d35ff8db2dece4e0593979d3ac223"
)

# STEPBible's filenames carry their own licence statement and are spelled
# differently between the two testaments ("CC BY" against "CC-BY"), so they are
# built here rather than written out four more times.
TAGGED = "Translators%20Amalgamated%20OT%2BNT"


def _tahot(span: str) -> str:
    return (
        f"{STEPBIBLE}/{TAGGED}/TAHOT%20{span}%20-%20Translators%20Amalgamated"
        "%20Hebrew%20OT%20-%20STEPBible.org%20CC%20BY.txt"
    )


def _tagnt(span: str) -> str:
    return (
        f"{STEPBIBLE}/{TAGGED}/TAGNT%20{span}%20-%20Translators%20Amalgamated"
        "%20Greek%20NT%20-%20STEPBible.org%20CC-BY.txt"
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
    (
        "TAHOT-Gen-Deu.txt",
        _tahot("Gen-Deu"),
        "e9b8546ee48fe0bfc57c3b70f5f40e98d96580e803526d19026224e31753368b",
    ),
    (
        "TAHOT-Jos-Est.txt",
        _tahot("Jos-Est"),
        "195fee1dc3653bab33701f170734eb894ed647c10cd08cc61749375fe8b73775",
    ),
    (
        "TAHOT-Job-Sng.txt",
        _tahot("Job-Sng"),
        "84e118a97e5725e3847cdfdd593873513021c790c63cc91a0d41fca2b5db2ed5",
    ),
    (
        "TAHOT-Isa-Mal.txt",
        _tahot("Isa-Mal"),
        "f3ded203d2a74d6368932c97ae550d1d0754b271af491dc0dedf36fe3ba0bcc5",
    ),
    (
        "TAGNT-Mat-Jhn.txt",
        _tagnt("Mat-Jhn"),
        "ab8eaaeb68e17a1dcfa34e1e9350358f22f03bc2a97244d848750ad81044bc8e",
    ),
    (
        "TAGNT-Act-Rev.txt",
        _tagnt("Act-Rev"),
        "524e32375361e6d3fa2f7ef00b87605fdc4317a762f395651a05fdc31ad031b7",
    ),
    (
        "TEHMC.txt",
        (
            f"{STEPBIBLE}/Morphology%20codes/TEHMC%20-%20Translators%20Expansion"
            "%20of%20Hebrew%20Morphology%20Codes%20-%20STEPBible.org%20CC%20BY.txt"
        ),
        "78779bea824b31d4467dec0161d547481c86f266bc39def12cd11dc7dcbe6da7",
    ),
    (
        "TEGMC.txt",
        # "Morphhology" is upstream's spelling, and the URL only resolves with it.
        (
            f"{STEPBIBLE}/Morphology%20codes/TEGMC%20-%20Translators%20Expansion"
            "%20of%20Greek%20Morphhology%20Codes%20-%20STEPBible.org%20CC%20BY.txt"
        ),
        "5f0416f7617019a6082285214903bde569a980d5fd3b88b8d7020d944e94de82",
    ),
    (
        "strongs-hebrew-dictionary.js",
        f"{STRONGS}/hebrew/strongs-hebrew-dictionary.js",
        "5ce6aeed551c709f49bcfa341cadf2f34bc7599b85d9de9e6ac2ecbf60fc3739",
    ),
    (
        "strongs-greek-dictionary.js",
        f"{STRONGS}/greek/strongs-greek-dictionary.js",
        "7624ee738ae47e80f1a352223e28a26d011c9cd4898822cee52f47a010c04efd",
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
