#!/usr/bin/env python3
"""Build data/concordance.db from the downloaded public-domain sources.

    python etl/fetch_sources.py
    python etl/build_db.py

Idempotent: it writes a fresh database each run (--out to change the path).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import books as bk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

TRANSLATIONS = [
    # code, name, year, license, source
    (
        "KJV",
        "King James Version",
        "1611/1769",
        "Public domain",
        "scrollmapper/bible_databases",
    ),
    (
        "ASV",
        "American Standard Version",
        "1901",
        "Public domain",
        "scrollmapper/bible_databases",
    ),
    (
        "WEB",
        "World English Bible",
        "2000",
        "Public domain",
        "seven1m/open-bibles (USFX)",
    ),
    (
        "BSB",
        "Berean Standard Bible",
        "2020",
        "Public domain",
        "scrollmapper/bible_databases",
    ),
]


# --------------------------------------------------------------------------
# translations
# --------------------------------------------------------------------------

def load_scrollmapper(path: Path, translation: str):
    """Yield (book_code, chapter, verse, text) from a scrollmapper JSON file."""
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    unknown = set()
    for book in data["books"]:
        code = bk.resolve(book["name"])
        if code is None:
            unknown.add(book["name"])
            continue
        for chapter in book["chapters"]:
            cnum = int(chapter["chapter"])
            for verse in chapter["verses"]:
                text = clean(verse["text"])
                if text:
                    yield code, cnum, int(verse["verse"]), text
    if unknown:
        print(f"    ! {translation}: unmapped books {sorted(unknown)}", file=sys.stderr)


# USFX elements whose contents are apparatus, not scripture text.
USFX_SKIP = {"f", "x", "fig", "ref", "rq", "fr", "ft", "fk", "fv", "xo", "xt"}


def load_usfx(path: Path):
    """Yield (book_code, chapter, verse, text) from a USFX XML bible."""
    tree = ET.parse(path)
    for book_el in tree.getroot().iter("book"):
        code = bk.resolve(book_el.get("id", ""))
        if code is None:
            continue
        state = {"chapter": 0, "verse": 0, "buf": []}
        rows: list[tuple[str, int, int, str]] = []

        def flush() -> None:
            if state["verse"] and state["buf"]:
                text = clean("".join(state["buf"]))
                if text:
                    rows.append((code, state["chapter"], state["verse"], text))
            state["buf"] = []
            state["verse"] = 0

        def walk(el) -> None:
            tag = el.tag
            if tag in USFX_SKIP:
                if el.tail and state["verse"]:
                    state["buf"].append(el.tail)
                return
            if tag == "c":
                flush()
                state["chapter"] = int(el.get("id", "0") or 0)
            elif tag == "v":
                flush()
                state["verse"] = int(re.sub(r"\D", "", el.get("id", "0")) or 0)
            elif tag == "ve":
                flush()
            if el.text and state["verse"]:
                state["buf"].append(el.text)
            for child in el:
                walk(child)
            if el.tail and state["verse"]:
                state["buf"].append(el.tail)

        for child in book_el:
            walk(child)
        flush()
        yield from rows


def clean(text: str) -> str:
    """Collapse whitespace and drop leftover markup artefacts."""
    text = re.sub(r"\s+", " ", text or "")
    text = re.sub(r"\s+([,;:.!?])", r"\1", text)
    return text.strip()


# --------------------------------------------------------------------------
# Nave's Topical Bible
# --------------------------------------------------------------------------

# A book code (2-4 caps, optional leading 1-3) immediately before a digit, or a
# chapter[:verse[-verse][,verse...]] group. Scanned left to right so a bare
# "23:13" inherits the book code that preceded it.
NAVE_TOKEN = re.compile(
    r"(?P<book>\b[1-3]?[A-Z]{2,4})(?=\s+\d)"
    r"|(?P<ref>\d+(?::\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*)?)"
)
VERSE_GROUP = re.compile(r"(\d+)(?:\s*[-–]\s*(\d+))?")


def parse_nave_line(line: str):
    """Yield (book, chapter, verse_start, verse_end) for one Nave's entry line.

    verse_start == 0 means the reference is to a whole chapter.
    """
    current = None
    for m in NAVE_TOKEN.finditer(line):
        if m.group("book"):
            code = bk.resolve(m.group("book"))
            if code:
                current = code
            continue
        if current is None:
            continue  # a number in the heading text, before any book code
        ref = m.group("ref")
        if ":" not in ref:
            yield current, int(ref), 0, 0
            continue
        chapter_s, verses_s = ref.split(":", 1)
        chapter = int(chapter_s)
        for vm in VERSE_GROUP.finditer(verses_s):
            start = int(vm.group(1))
            end = int(vm.group(2)) if vm.group(2) else start
            yield current, chapter, start, end


def format_ref(book: str, chapter: int, start: int, end: int) -> str:
    if start == 0:
        return f"{book}.{chapter}"
    if end > start:
        return f"{book}.{chapter}.{start}-{end}"
    return f"{book}.{chapter}.{start}"


def load_naves(path: Path, valid: dict[tuple[str, int], int]):
    """Yield (topic, section, heading, book, chapter, start, end) rows.

    `valid` maps (book, chapter) -> highest verse number, used to throw out
    references the parser mis-read out of the prose headings.
    """
    dropped = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            topic = (row.get("subject") or "").strip()
            entry = row.get("entry") or ""
            if not topic:
                continue
            for line in entry.splitlines():
                line = line.strip()
                if not line:
                    continue
                heading = line.lstrip("-").strip()
                # the heading is the prose before the first reference
                first = NAVE_TOKEN.search(line)
                if first:
                    heading = line[: first.start()].lstrip("-").strip(" ,;")
                for book, chapter, start, end in parse_nave_line(line):
                    last = valid.get((book, chapter))
                    if last is None or start > last or end > last:
                        dropped += 1
                        continue
                    yield topic, (row.get("section") or "").strip(), heading, book, chapter, start, end
    if dropped:
        print(f"    dropped {dropped:,} references that do not resolve to a verse")


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

NOTE_COLUMNS = (
    "id, verse_ref, book, chapter, verse, translation, body, created_at, updated_at"
)


def rescue_notes(db_path: Path) -> list[tuple]:
    """Read personal notes out of the database that is about to be replaced.

    Scripture can always be rebuilt from the sources; notes cannot. Opening the
    database properly (rather than copying the file) also picks up anything
    still sitting in the WAL.
    """
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    try:
        con.execute("SELECT 1 FROM notes LIMIT 1")
        return con.execute(f"SELECT {NOTE_COLUMNS} FROM notes ORDER BY id").fetchall()
    except sqlite3.DatabaseError:
        return []  # older or corrupt file with no notes table
    finally:
        con.close()


def require_fts5() -> None:
    """Fail here, with a sentence, rather than deep in schema.sql."""
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError as exc:
        raise SystemExit(
            "this Python's SQLite was built without FTS5, which the whole app "
            f"rests on ({exc}). Use a python.org build or a distro package."
        ) from exc
    finally:
        probe.close()


def build(db_path: Path) -> None:
    require_fts5()
    saved_notes = rescue_notes(db_path)
    if saved_notes:
        print(f"holding on to {len(saved_notes):,} note(s) across the rebuild")

    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        stale = db_path.with_name(db_path.name + suffix)
        if stale.exists():
            stale.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA.read_text())

    con.executemany(
        "INSERT INTO books(code, name, ordinal, testament) VALUES (?,?,?,?)",
        [(c, bk.NAME[c], bk.ORDINAL[c], bk.testament(c)) for c in bk.CODES],
    )
    con.executemany(
        "INSERT INTO translations(code, name, year, license, source) VALUES (?,?,?,?,?)",
        TRANSLATIONS,
    )

    print("verses:")
    for code, name, *_ in TRANSLATIONS:
        src = SOURCES / ("eng-web.usfx.xml" if code == "WEB" else f"{code}.json")
        if not src.exists():
            raise SystemExit(f"missing source {src} -- run etl/fetch_sources.py first")
        rows = load_usfx(src) if code == "WEB" else load_scrollmapper(src, code)
        con.executemany(
            "INSERT OR IGNORE INTO verses(book, chapter, verse, translation, text)"
            " VALUES (?,?,?,?,?)",
            ((b, c, v, code, t) for b, c, v, t in rows),
        )
        n = con.execute(
            "SELECT count(*) FROM verses WHERE translation = ?", (code,)
        ).fetchone()[0]
        print(f"  {code:<4} {n:>7,}  {name}")

    print("indexing verse text (FTS5)...")
    con.execute("INSERT INTO verses_fts(rowid, text) SELECT id, text FROM verses")

    # Reference sanity check for Nave's, based on the fullest translation.
    valid = {
        (b, c): last
        for b, c, last in con.execute(
            "SELECT book, chapter, max(verse) FROM verses GROUP BY book, chapter"
        )
    }

    print("topics:")
    naves = SOURCES / "NavesTopicalDictionary.csv"
    if not naves.exists():
        raise SystemExit(f"missing source {naves} -- run etl/fetch_sources.py first")

    topic_ids: dict[str, int] = {}
    seq: dict[int, int] = {}
    batch = []
    for topic, section, heading, book, chapter, start, end in load_naves(naves, valid):
        tid = topic_ids.get(topic)
        if tid is None:
            cur = con.execute(
                "INSERT INTO topics(name, section) VALUES (?,?)", (topic, section)
            )
            tid = topic_ids[topic] = cur.lastrowid
            seq[tid] = 0
        seq[tid] += 1
        batch.append(
            (
                tid,
                format_ref(book, chapter, start, end),
                book,
                chapter,
                start,
                end,
                heading or None,
                seq[tid],
            )
        )
        if len(batch) >= 5000:
            _flush_topic_verses(con, batch)
    _flush_topic_verses(con, batch)

    con.execute("INSERT INTO topics_fts(rowid, name) SELECT id, name FROM topics")

    n_topics = con.execute("SELECT count(*) FROM topics").fetchone()[0]
    n_refs = con.execute("SELECT count(*) FROM topic_verses").fetchone()[0]
    print(f"  {n_topics:,} topics, {n_refs:,} references")

    if saved_notes:
        placeholders = ",".join("?" * len(saved_notes[0]))
        con.executemany(
            f"INSERT INTO notes({NOTE_COLUMNS}) VALUES ({placeholders})", saved_notes
        )
        kept = con.execute("SELECT count(*) FROM notes").fetchone()[0]
        print(f"  restored {kept:,} note(s)")

    con.commit()
    con.execute("PRAGMA optimize")
    con.execute("VACUUM")
    con.close()
    size = db_path.stat().st_size
    print(f"wrote {db_path} ({size / 1e6:.1f} MB)")


def _flush_topic_verses(con: sqlite3.Connection, batch: list) -> None:
    if batch:
        con.executemany(
            "INSERT INTO topic_verses(topic_id, verse_ref, book, chapter,"
            " verse_start, verse_end, heading, seq) VALUES (?,?,?,?,?,?,?,?)",
            batch,
        )
        batch.clear()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data" / "concordance.db"))
    args = ap.parse_args()
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
