"""Concordance API.

Read-only scripture + Nave's topical index out of SQLite/FTS5, plus personal
notes that live in the same database. Nothing here talks to the network; the
translations were pulled once at setup by etl/fetch_sources.py.
"""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, embeddings, originals, refs, search

app = FastAPI(title="Concordance", version="1.0", docs_url="/api/docs")

# The SPA is served from this process in production; in development Vite runs
# on :5173 and proxies /api here, so allow it through.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Display order for the filter chips. Which codes are *valid* comes from the
# translations table, so adding a translation to the ETL is enough; this list
# only decides the order they appear in.
TRANSLATION_CHIPS = ["ALL", "KJV", "ASV", "WEB", "BSB"]

_valid_translations: set[str] | None = None


def valid_translations(con: sqlite3.Connection) -> set[str]:
    """The translation codes the database holds, read once and kept."""
    global _valid_translations
    if _valid_translations is None:
        _valid_translations = {
            r["code"] for r in con.execute("SELECT code FROM translations")
        }
    return _valid_translations


# Loaded once from the request that first needs it: 31k verses' worth of
# vectors, held in memory rather than re-read from SQLite every search.
_meaning_index: embeddings.MeaningIndex | None = None
_meaning_index_loaded = False


def meaning_index(con: sqlite3.Connection) -> embeddings.MeaningIndex | None:
    global _meaning_index, _meaning_index_loaded
    if not _meaning_index_loaded:
        _meaning_index = embeddings.load(con)
        _meaning_index_loaded = True
    return _meaning_index


# Strong's dictionary is read-only and small enough to hold in memory,
# accent-folded, for lookup: a transliteration carries marks ("lógos") a
# person typing "logos" on an English keyboard has no way to reproduce.
_strongs_folded: list[tuple[sqlite3.Row, str, str, str]] | None = None


def strongs_folded(con: sqlite3.Connection) -> list[tuple[sqlite3.Row, str, str, str]]:
    global _strongs_folded
    if _strongs_folded is None:
        _strongs_folded = [
            (r, originals.fold(r["translit"] or ""), originals.fold(r["lemma"] or ""),
             originals.fold(r["definition"] or ""))
            for r in con.execute("SELECT * FROM strongs_entries")
        ]
    return _strongs_folded


def chip_order(con: sqlite3.Connection) -> list[str]:
    codes = valid_translations(con)
    known = [c for c in TRANSLATION_CHIPS if c == "ALL" or c in codes]
    return known + sorted(codes - set(TRANSLATION_CHIPS))


def get_db():
    con = db.connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def verse_row(row: sqlite3.Row, marked: bool = False) -> dict:
    text = row["marked"] if marked else row["text"]
    out = {
        "id": row["id"],
        "ref": f"{row['book']}.{row['chapter']}.{row['verse']}",
        "book": row["book"],
        "book_name": row["book_name"],
        "chapter": row["chapter"],
        "verse": row["verse"],
        "translation": row["translation"],
        "text": text.replace(search.MARK_OPEN, "").replace(search.MARK_CLOSE, ""),
    }
    if marked:
        out["segments"] = search.split_marks(text)
    return out


def check_translation(con: sqlite3.Connection, translation: str) -> str:
    t = (translation or "ALL").upper()
    if t != "ALL" and t not in valid_translations(con):
        raise HTTPException(400, f"unknown translation {translation!r}")
    return t


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------

@app.get("/api/meta")
def meta(con: sqlite3.Connection = Depends(get_db)):
    """Translations, books and chapter counts -- everything the UI needs up front."""
    translations = [dict(r) for r in con.execute("SELECT * FROM translations")]
    order = {t: i for i, t in enumerate(chip_order(con))}
    translations.sort(key=lambda t: order.get(t["code"], 99))

    books = [
        {
            "code": r["code"],
            "name": r["name"],
            "ordinal": r["ordinal"],
            "testament": r["testament"],
            "chapters": r["chapters"],
        }
        for r in con.execute(
            """SELECT b.code, b.name, b.ordinal, b.testament,
                      (SELECT max(chapter) FROM verses v WHERE v.book = b.code) AS chapters
               FROM books b ORDER BY b.ordinal"""
        )
    ]
    counts = {
        r["translation"]: r["n"]
        for r in con.execute(
            "SELECT translation, count(*) AS n FROM verses GROUP BY translation"
        )
    }
    return {
        "translations": translations,
        "translation_chips": chip_order(con),
        "books": [b for b in books if b["chapters"]],
        "verse_counts": counts,
        "topic_count": con.execute("SELECT count(*) FROM topics").fetchone()[0],
    }


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------

@app.get("/api/search")
def api_search(
    q: str = Query("", description="free text"),
    translation: str = Query("ALL"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort: str = Query("relevance", pattern="^(relevance|canonical)$"),
    mode: str = Query("meaning", pattern="^(meaning|exact|strongs)$"),
    include: str = Query("verses,topics,notes"),
    con: sqlite3.Connection = Depends(get_db),
):
    """Full-text search over verses, Nave's topic names and personal notes.

    `mode` shapes the verse results. "exact" is FTS5 alone, the way search
    always worked. "meaning" (the default) adds verses the on-device LSA
    index calls close in sense even where they share no words -- each verse
    comes back tagged with `match_kind` so the client can tell exact hits
    from meaning-only ones. "strongs" treats the query as naming a Hebrew or
    Greek word rather than English text: it skips the verse search and
    widens the dictionary lookup from an exact number to a lemma or
    transliteration match too.
    """
    translation = check_translation(con, translation)
    match = search.build_match(q)
    wanted = {p.strip() for p in include.split(",")}
    empty = {
        "query": q,
        "translation": translation,
        "mode": mode,
        "verses": [],
        "verse_total": 0,
        "topics": [],
        "notes": [],
        "strongs": None,
        "strongs_matches": [],
        "reference": None,
    }
    if not match:
        return empty

    result = dict(empty)

    # "John 3:16" is not a text query either: a reference-shaped search hands
    # back the verse itself as a card above the text hits -- alongside the
    # ordinary results, not instead of them, the same shape as the Strong's
    # entry below, so a query that merely looks like a reference still runs.
    parsed = refs.parse_human(q)
    if parsed is not None:
        result["reference"] = reference_card(con, parsed, translation)

    # "G26" is not a word anybody is searching the English text for. Hand back
    # the dictionary entry alongside the ordinary results rather than instead
    # of them, so a search that looks like a number but isn't still works.
    key = originals.parse_strongs(q)
    if key:
        row = con.execute(
            "SELECT * FROM strongs_entries WHERE id = ?", [key]
        ).fetchone()
        if row is not None:
            entry = originals.entry_row(row)
            entry["occurrences"] = con.execute(
                "SELECT count(*) FROM original_words WHERE strongs_base = ?", [key]
            ).fetchone()[0]
            result["strongs"] = entry

    # "Strong's" mode reads the query as naming a Hebrew or Greek word rather
    # than English text: a transliteration or lemma fragment ("logos") widens
    # past the exact-number lookup above. Folded to strip transliteration
    # accents ("lógos") an English keyboard can't type.
    if mode == "strongs":
        needle = originals.fold(" ".join(search.parse_terms(q)))
        if needle:
            hits = [
                (r, translit == needle, translit.startswith(needle))
                for r, translit, lemma, definition in strongs_folded(con)
                if needle in translit or needle in lemma or needle in definition
            ]
            hits.sort(key=lambda h: (not h[1], not h[2], len(h[0]["translit"] or "")))
            top = hits[:12]
            matches = [originals.entry_row(r) for r, *_ in top]
            for m, (r, *_) in zip(matches, top):
                m["occurrences"] = con.execute(
                    "SELECT count(*) FROM original_words WHERE strongs_base = ?",
                    [r["id"]],
                ).fetchone()[0]
            result["strongs_matches"] = matches

    if "verses" in wanted and mode != "strongs":
        where = "verses_fts MATCH ?"
        params: list = [match]
        if translation != "ALL":
            where += " AND v.translation = ?"
            params.append(translation)

        order = (
            "bm25(verses_fts), b.ordinal, v.chapter, v.verse, v.translation"
            if sort == "relevance"
            else "b.ordinal, v.chapter, v.verse, v.translation"
        )
        rows = con.execute(
            f"""SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                       b.name AS book_name,
                       highlight(verses_fts, 0, ?, ?) AS marked
                FROM verses_fts
                JOIN verses v ON v.id = verses_fts.rowid
                JOIN books  b ON b.code = v.book
                WHERE {where}
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
            [search.MARK_OPEN, search.MARK_CLOSE, *params, limit, offset],
        ).fetchall()
        result["verses"] = [verse_row(r, marked=True) for r in rows]
        for v in result["verses"]:
            v["match_kind"] = "exact"
        result["verse_total"] = con.execute(
            f"""SELECT count(*) FROM verses_fts
                JOIN verses v ON v.id = verses_fts.rowid
                WHERE {where}""",
            params,
        ).fetchone()[0]

        # Meaning results ride along on the first page only -- they are not
        # part of the FTS ranking "Load more" pages through, just a fixed set
        # of neighbours shown alongside it. `verse_total` stays the true FTS
        # count throughout: it is also the paging bound "Load more" uses to
        # ask for the next slice of *FTS* results, and inflating it with a
        # one-off batch of meaning-only extras would either overstate the
        # match count after page 2 (which carries no extras) or make the
        # client ask the FTS query for an offset past its real result set.
        if mode == "meaning" and offset == 0:
            index = meaning_index(con)
            if index is not None:
                seen = {(v["book"], v["chapter"], v["verse"]) for v in result["verses"]}
                meaning_translation = translation if translation != "ALL" else "KJV"
                extra = []
                for (b, c, vs), score in index.nearest(q, limit=limit * 4):
                    if (b, c, vs) in seen or score < 0.35:
                        continue
                    row = con.execute(
                        """SELECT vv.id, vv.book, vv.chapter, vv.verse, vv.translation,
                                  vv.text, bb.name AS book_name
                           FROM verses vv JOIN books bb ON bb.code = vv.book
                           WHERE vv.book = ? AND vv.chapter = ? AND vv.verse = ?
                             AND vv.translation = ?""",
                        [b, c, vs, meaning_translation],
                    ).fetchone()
                    if row is None:
                        continue
                    seen.add((b, c, vs))
                    vr = verse_row(row)
                    vr["match_kind"] = "meaning"
                    vr["score"] = round(score, 3)
                    extra.append(vr)
                    if len(extra) >= limit:
                        break
                result["verses"].extend(extra)

    if "topics" in wanted:
        result["topics"] = topic_matches(con, q, limit=12)

    if "notes" in wanted:
        result["notes"] = [
            note_row(r, marked=True)
            for r in con.execute(
                """SELECT n.*, b.name AS book_name,
                          highlight(notes_fts, 0, ?, ?) AS marked
                   FROM notes_fts
                   JOIN notes n ON n.id = notes_fts.rowid
                   JOIN books b ON b.code = n.book
                   WHERE notes_fts MATCH ?
                   ORDER BY bm25(notes_fts)
                   LIMIT 20""",
                [search.MARK_OPEN, search.MARK_CLOSE, match],
            )
        ]

    return result


def reference_card(
    con: sqlite3.Connection, parsed: refs.Ref, translation: str
) -> dict | None:
    """The verse (or chapter) a reference-shaped query names, if it exists.

    A whole-chapter reference carries no text -- the card is a doorway into the
    reader, not the chapter itself. A verse or range brings its text along, in
    the searched translation or all of them, capped so PSA.119.1-176 across
    four translations doesn't arrive as one enormous card.
    """
    book = con.execute(
        "SELECT name FROM books WHERE code = ?", [parsed.book]
    ).fetchone()
    if book is None:
        return None
    out = {
        "ref": str(parsed),
        "label": refs.label(book["name"], parsed),
        "book": parsed.book,
        "book_name": book["name"],
        "chapter": parsed.chapter,
        "verse_start": parsed.verse_start,
        "verse_end": parsed.verse_end,
        "verses": [],
    }
    if not parsed.verse_start:
        exists = con.execute(
            "SELECT 1 FROM verses WHERE book = ? AND chapter = ? LIMIT 1",
            [parsed.book, parsed.chapter],
        ).fetchone()
        return out if exists else None
    sql = """SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                    b.name AS book_name
             FROM verses v JOIN books b ON b.code = v.book
             WHERE v.book = ? AND v.chapter = ? AND v.verse BETWEEN ? AND ?"""
    params: list = [parsed.book, parsed.chapter, parsed.verse_start, parsed.verse_end]
    if translation != "ALL":
        sql += " AND v.translation = ?"
        params.append(translation)
    rows = con.execute(
        sql + " ORDER BY v.verse, v.translation LIMIT 20", params
    ).fetchall()
    if not rows:
        return None
    out["verses"] = [verse_row(r) for r in rows]
    return out


def topic_matches(
    con: sqlite3.Connection, q: str, limit: int, offset: int = 0
) -> list[dict]:
    """Nave's topics whose *name* matches, with how many references each holds.

    Two ways in: the (unstemmed) FTS index for word and prefix hits, and a plain
    substring match so a fragment mid-word still finds the topic. Ranked so an
    exact name comes first, then names that start with what was typed.
    """
    match = search.build_match(q, stem=False)
    if not match:
        return []
    terms = search.parse_terms(q)
    needle = " ".join(terms)
    rows = con.execute(
        """SELECT t.id, t.name, t.section,
                  (SELECT count(*) FROM topic_verses tv WHERE tv.topic_id = t.id)
                    AS ref_count
           FROM topics t
           WHERE t.id IN (SELECT rowid FROM topics_fts WHERE topics_fts MATCH ?)
              OR t.name LIKE ?
           ORDER BY (lower(t.name) = lower(?)) DESC,
                    (lower(t.name) LIKE lower(?) || '%') DESC,
                    length(t.name),
                    ref_count DESC
           LIMIT ? OFFSET ?""",
        [match, f"%{needle}%", needle, needle, limit, offset],
    )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "section": r["section"],
            "ref_count": r["ref_count"],
        }
        for r in rows
    ]


# --------------------------------------------------------------------------
# topics
# --------------------------------------------------------------------------

@app.get("/api/topics")
def list_topics(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    con: sqlite3.Connection = Depends(get_db),
):
    if q.strip():
        return {
            "topics": topic_matches(con, q, limit=limit, offset=offset),
            "query": q,
        }
    rows = con.execute(
        """SELECT t.id, t.name, t.section,
                  (SELECT count(*) FROM topic_verses tv WHERE tv.topic_id = t.id)
                    AS ref_count
           FROM topics t
           ORDER BY ref_count DESC, t.name
           LIMIT ? OFFSET ?""",
        [limit, offset],
    )
    return {"topics": [dict(r) for r in rows], "query": q}


@app.get("/api/topics/{topic_id}")
def get_topic(
    topic_id: int,
    translation: str = Query("KJV"),
    con: sqlite3.Connection = Depends(get_db),
):
    """A topic with every reference Nave's files under it, verse text attached."""
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    topic = con.execute("SELECT * FROM topics WHERE id = ?", [topic_id]).fetchone()
    if topic is None:
        raise HTTPException(404, "topic not found")

    rows = con.execute(
        """SELECT tv.verse_ref, tv.book, tv.chapter, tv.verse_start, tv.verse_end,
                  tv.heading, tv.seq, b.name AS book_name,
                  (SELECT v.text FROM verses v
                    WHERE v.translation = ? AND v.book = tv.book
                      AND v.chapter = tv.chapter
                      AND v.verse = CASE WHEN tv.verse_start = 0 THEN 1
                                         ELSE tv.verse_start END) AS text
           FROM topic_verses tv
           JOIN books b ON b.code = tv.book
           WHERE tv.topic_id = ?
           ORDER BY tv.seq""",
        [translation, topic_id],
    ).fetchall()

    groups: list[dict] = []
    for r in rows:
        heading = r["heading"] or ""
        if not groups or groups[-1]["heading"] != heading:
            groups.append({"heading": heading, "refs": []})
        groups[-1]["refs"].append(
            {
                "ref": r["verse_ref"],
                "book": r["book"],
                "book_name": r["book_name"],
                "chapter": r["chapter"],
                "verse_start": r["verse_start"],
                "verse_end": r["verse_end"],
                "label": refs.label(
                    r["book_name"],
                    refs.Ref(r["book"], r["chapter"], r["verse_start"], r["verse_end"]),
                ),
                "text": r["text"],
            }
        )

    return {
        "id": topic["id"],
        "name": topic["name"],
        "section": topic["section"],
        "translation": translation,
        "ref_count": len(rows),
        "groups": groups,
    }


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

@app.get("/api/chapter/{book}/{chapter}")
def get_chapter(
    book: str,
    chapter: int,
    translation: str = Query("KJV"),
    con: sqlite3.Connection = Depends(get_db),
):
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    book = book.upper()
    meta_row = con.execute("SELECT * FROM books WHERE code = ?", [book]).fetchone()
    if meta_row is None:
        raise HTTPException(404, "book not found")

    rows = con.execute(
        """SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                  b.name AS book_name
           FROM verses v JOIN books b ON b.code = v.book
           WHERE v.translation = ? AND v.book = ? AND v.chapter = ?
           ORDER BY v.verse""",
        [translation, book, chapter],
    ).fetchall()
    if not rows:
        raise HTTPException(404, "chapter not found")

    noted = {
        r["verse"]: r["n"]
        for r in con.execute(
            """SELECT verse, count(*) AS n FROM notes
               WHERE book = ? AND chapter = ? GROUP BY verse""",
            [book, chapter],
        )
    }
    highlighted = {
        r[0]
        for r in con.execute(
            "SELECT verse FROM highlights WHERE book = ? AND chapter = ?",
            [book, chapter],
        )
    }
    threaded: set[int] = set()
    for start, end in con.execute(
        "SELECT verse_start, verse_end FROM thread_items WHERE book = ? AND chapter = ?",
        [book, chapter],
    ):
        threaded.update(range(start, end + 1))
    verses = []
    for r in rows:
        v = verse_row(r)
        v["note_count"] = noted.get(r["verse"], 0)
        v["highlighted"] = r["verse"] in highlighted
        v["in_thread"] = r["verse"] in threaded
        verses.append(v)

    last_chapter = con.execute(
        "SELECT max(chapter) FROM verses WHERE book = ? AND translation = ?",
        [book, translation],
    ).fetchone()[0]

    return {
        "book": book,
        "book_name": meta_row["name"],
        "chapter": chapter,
        "chapters": last_chapter,
        "translation": translation,
        "label": f"{meta_row['name']} {chapter}",
        "prev": neighbour(con, meta_row["ordinal"], chapter, translation, -1),
        "next": neighbour(con, meta_row["ordinal"], chapter, translation, +1),
        "verses": verses,
    }


def neighbour(
    con: sqlite3.Connection, ordinal: int, chapter: int, translation: str, step: int
) -> dict | None:
    """The previous/next chapter, rolling over book boundaries."""
    if step < 0 and chapter > 1:
        return {"book": book_by_ordinal(con, ordinal), "chapter": chapter - 1}
    if step > 0:
        code = book_by_ordinal(con, ordinal)
        last = con.execute(
            "SELECT max(chapter) FROM verses WHERE book = ? AND translation = ?",
            [code, translation],
        ).fetchone()[0]
        if chapter < (last or 0):
            return {"book": code, "chapter": chapter + 1}
    code = book_by_ordinal(con, ordinal + step)
    if code is None:
        return None
    if step > 0:
        return {"book": code, "chapter": 1}
    last = con.execute(
        "SELECT max(chapter) FROM verses WHERE book = ? AND translation = ?",
        [code, translation],
    ).fetchone()[0]
    return {"book": code, "chapter": last} if last else None


def book_by_ordinal(con: sqlite3.Connection, ordinal: int) -> str | None:
    row = con.execute("SELECT code FROM books WHERE ordinal = ?", [ordinal]).fetchone()
    return row["code"] if row else None


@app.get("/api/verse/{ref}")
def get_verse(
    ref: str,
    translation: str = Query("ALL"),
    con: sqlite3.Connection = Depends(get_db),
):
    """One verse in one or every translation -- used by the note editor."""
    translation = check_translation(con, translation)
    parsed = refs.parse(ref)
    if parsed is None or not parsed.verse_start:
        raise HTTPException(400, "expected a reference like PHP.4.6")
    sql = """SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                    b.name AS book_name
             FROM verses v JOIN books b ON b.code = v.book
             WHERE v.book = ? AND v.chapter = ? AND v.verse BETWEEN ? AND ?"""
    params = [parsed.book, parsed.chapter, parsed.verse_start, parsed.verse_end]
    if translation != "ALL":
        sql += " AND v.translation = ?"
        params.append(translation)
    rows = con.execute(sql + " ORDER BY v.verse, v.translation", params).fetchall()
    if not rows:
        raise HTTPException(404, "verse not found")
    return {
        "ref": str(parsed),
        "label": refs.label(rows[0]["book_name"], parsed),
        "verses": [verse_row(r) for r in rows],
    }


@app.get("/api/cross-refs/{ref}")
def cross_refs(
    ref: str,
    translation: str = Query("KJV"),
    con: sqlite3.Connection = Depends(get_db),
):
    """Related verses, by way of the Nave's topics this verse is filed under.

    There is no separate cross-reference dataset in v1: two verses are related
    when Nave's puts them under the same topic.
    """
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    parsed = refs.parse(ref)
    if parsed is None or not parsed.verse_start:
        raise HTTPException(400, "expected a reference like PHP.4.6")

    topics = con.execute(
        """SELECT DISTINCT t.id, t.name,
                  (SELECT count(*) FROM topic_verses x WHERE x.topic_id = t.id)
                    AS ref_count
           FROM topic_verses tv
           JOIN topics t ON t.id = tv.topic_id
           WHERE tv.book = ? AND tv.chapter = ?
             AND (tv.verse_start = 0
                  OR (? BETWEEN tv.verse_start AND tv.verse_end))
           ORDER BY ref_count
           LIMIT 8""",
        [parsed.book, parsed.chapter, parsed.verse_start],
    ).fetchall()

    out = []
    for t in topics:
        siblings = con.execute(
            """SELECT tv.verse_ref, tv.book, tv.chapter, tv.verse_start,
                      tv.verse_end, b.name AS book_name,
                      (SELECT v.text FROM verses v
                        WHERE v.translation = ? AND v.book = tv.book
                          AND v.chapter = tv.chapter
                          AND v.verse = CASE WHEN tv.verse_start = 0 THEN 1
                                             ELSE tv.verse_start END) AS text
               FROM topic_verses tv
               JOIN books b ON b.code = tv.book
               WHERE tv.topic_id = ?
                 AND NOT (tv.book = ? AND tv.chapter = ?
                          AND (tv.verse_start = 0
                               OR (? BETWEEN tv.verse_start AND tv.verse_end)))
               ORDER BY tv.seq
               LIMIT 6""",
            [
                translation,
                t["id"],
                parsed.book,
                parsed.chapter,
                parsed.verse_start,
            ],
        ).fetchall()
        if not siblings:
            continue
        out.append(
            {
                "topic_id": t["id"],
                "topic": t["name"],
                "ref_count": t["ref_count"],
                "refs": [
                    {
                        "ref": s["verse_ref"],
                        "label": refs.label(
                            s["book_name"],
                            refs.Ref(
                                s["book"], s["chapter"], s["verse_start"], s["verse_end"]
                            ),
                        ),
                        "book": s["book"],
                        "chapter": s["chapter"],
                        "verse_start": s["verse_start"],
                        "text": s["text"],
                    }
                    for s in siblings
                ],
            }
        )
    return {"ref": str(parsed), "translation": translation, "topics": out}


# --------------------------------------------------------------------------
# original languages
# --------------------------------------------------------------------------

@app.get("/api/interlinear/{ref}")
def interlinear(
    ref: str,
    translation: str = Query("KJV"),
    con: sqlite3.Connection = Depends(get_db),
):
    """One verse word by word in Hebrew, Aramaic or Greek."""
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    parsed = refs.parse(ref)
    # A range has one original per verse, not one between them. Taking the
    # first and echoing the range back would label PHP.4.6's words PHP.4.6-7.
    if parsed is None or not parsed.verse_start or parsed.verse_end != parsed.verse_start:
        raise HTTPException(400, "expected a single verse, like PHP.4.6")

    row = con.execute(
        """SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                  b.name AS book_name
           FROM verses v JOIN books b ON b.code = v.book
           WHERE v.book = ? AND v.chapter = ? AND v.verse = ? AND v.translation = ?""",
        [parsed.book, parsed.chapter, parsed.verse_start, translation],
    ).fetchone()
    if row is None:
        raise HTTPException(404, "verse not found")

    rows = originals.words_for(con, parsed.book, parsed.chapter, parsed.verse_start)
    words = [originals.word_row(r) for r in rows]
    lang = words[0]["lang"] if words else None
    name, direction = originals.LANGUAGES.get(lang, ("", "ltr"))
    return {
        "ref": str(parsed),
        "label": refs.label(row["book_name"], parsed),
        "lang": lang,
        "language": name,
        "direction": direction,
        "verse": verse_row(row),
        "words": words,
    }


@app.get("/api/strongs/{number}")
def strongs_entry(number: str, con: sqlite3.Connection = Depends(get_db)):
    """A Strong's dictionary entry, with how the taggers read it in context."""
    key = originals.parse_strongs(number)
    if key is None:
        raise HTTPException(400, "expected a Strong's number like H2617 or G26")
    row = con.execute("SELECT * FROM strongs_entries WHERE id = ?", [key]).fetchone()
    if row is None:
        raise HTTPException(404, f"no Strong's entry {key}")

    out = originals.entry_row(row)
    out["occurrences"] = con.execute(
        "SELECT count(*) FROM original_words WHERE strongs_base = ?", [key]
    ).fetchone()[0]
    # What the word actually says in the places it stands, commonest first.
    # Strong's own "kjv_def" is a list; this is a count.
    out["senses"] = [
        {"gloss": r["sense"], "count": r["n"]}
        for r in con.execute(
            # The glosses carry the punctuation of the verse they came out of,
            # so "love", "love," and "Love" are one sense and have to be folded
            # together or the list is mostly commas. Brackets are left alone:
            # they mark words the translators supplied, and trimming one end
            # of "[the] word" leaves the other stranded. The alias is
            # deliberately not `gloss` -- GROUP BY would bind that to the
            # column, not to this.
            """SELECT lower(trim(gloss, ' .,;:!?')) AS sense, count(*) AS n
               FROM original_words
               WHERE strongs_base = ? AND trim(gloss, ' .,;:!?') <> ''
               GROUP BY sense ORDER BY n DESC, sense LIMIT 12""",
            [key],
        )
    ]
    out["histogram"] = strongs_histogram(con, key)
    return out


HISTOGRAM_BUCKETS = 24


def strongs_histogram(con: sqlite3.Connection, key: str) -> list[int]:
    """Occurrence counts across the canon, Genesis to Revelation, in fixed
    buckets -- the shape behind the small bar chart on a Strong's entry."""
    counts = [0] * HISTOGRAM_BUCKETS
    for ordinal, in con.execute(
        """SELECT b.ordinal FROM original_words w
           JOIN books b ON b.code = w.book
           WHERE w.strongs_base = ?""",
        [key],
    ):
        bucket = min(HISTOGRAM_BUCKETS - 1, (ordinal - 1) * HISTOGRAM_BUCKETS // 66)
        counts[bucket] += 1
    return counts


@app.get("/api/strongs/{number}/verses")
def strongs_verses(
    number: str,
    translation: str = Query("KJV"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    con: sqlite3.Connection = Depends(get_db),
):
    """Every verse the word stands in, Genesis to Revelation.

    This is the concordance the app is named for, running off the original
    rather than off an English spelling: one number, every place it is used,
    however the translators happened to render it.
    """
    key = originals.parse_strongs(number)
    if key is None:
        raise HTTPException(400, "expected a Strong's number like H2617 or G26")
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"

    # A Psalm superscription is filed as verse 0 and read at the head of verse
    # 1, so both resolve to the same reference. Folding them together before
    # grouping keeps a word used in both the title and the first line of a
    # Psalm from being listed twice and counted twice.
    total = con.execute(
        """SELECT count(*) FROM (SELECT DISTINCT book, chapter, max(verse, 1)
                                 FROM original_words WHERE strongs_base = ?)""",
        [key],
    ).fetchone()[0]

    rows = con.execute(
        """SELECT w.book, w.chapter, max(w.verse, 1) AS verse, b.name AS book_name,
                  count(*) AS hits,
                  group_concat(w.surface, ' ') AS surfaces,
                  group_concat(w.gloss, ' / ') AS glosses,
                  (SELECT v.text FROM verses v
                    WHERE v.translation = ? AND v.book = w.book
                      AND v.chapter = w.chapter AND v.verse = max(w.verse, 1)) AS text
           FROM original_words w
           JOIN books b ON b.code = w.book
           WHERE w.strongs_base = ?
           GROUP BY w.book, w.chapter, max(w.verse, 1)
           ORDER BY b.ordinal, w.chapter, max(w.verse, 1)
           LIMIT ? OFFSET ?""",
        [translation, key, limit, offset],
    ).fetchall()

    return {
        "id": key,
        "translation": translation,
        "total": total,
        "refs": [
            {
                "ref": f"{r['book']}.{r['chapter']}.{r['verse']}",
                "label": refs.label(
                    r["book_name"],
                    refs.Ref(r["book"], r["chapter"], r["verse"], r["verse"]),
                ),
                "book": r["book"],
                "chapter": r["chapter"],
                "verse": r["verse"],
                "hits": r["hits"],
                "surfaces": r["surfaces"],
                "glosses": r["glosses"],
                "text": r["text"],
            }
            for r in rows
        ],
    }


# --------------------------------------------------------------------------
# notes
# --------------------------------------------------------------------------

class NoteIn(BaseModel):
    verse_ref: str = Field(..., examples=["PHP.4.6"])
    body: str
    translation: str | None = None


class NotePatch(BaseModel):
    body: str


def note_row(r: sqlite3.Row, marked: bool = False) -> dict:
    body = r["marked"] if marked else r["body"]
    out = {
        "id": r["id"],
        "verse_ref": r["verse_ref"],
        "book": r["book"],
        "book_name": r["book_name"],
        "chapter": r["chapter"],
        "verse": r["verse"],
        "translation": r["translation"],
        "body": body.replace(search.MARK_OPEN, "").replace(search.MARK_CLOSE, ""),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    out["label"] = refs.label(
        r["book_name"], refs.Ref(r["book"], r["chapter"], r["verse"], r["verse"])
    )
    if marked:
        out["segments"] = search.split_marks(body)
    # sqlite3.Row membership tests values, not column names, so .keys() stays.
    if "verse_text" in r.keys():  # noqa: SIM118
        out["verse_text"] = r["verse_text"]
    return out


NOTE_SELECT = """
    SELECT n.*, b.name AS book_name,
           (SELECT v.text FROM verses v
             WHERE v.book = n.book AND v.chapter = n.chapter AND v.verse = n.verse
               AND v.translation = coalesce(n.translation, 'KJV')) AS verse_text
    FROM notes n JOIN books b ON b.code = n.book
"""


@app.get("/api/notes")
def list_notes(
    q: str = Query(""),
    ref: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    con: sqlite3.Connection = Depends(get_db),
):
    if ref:
        parsed = refs.parse(ref)
        if parsed is None:
            raise HTTPException(400, "bad reference")
        rows = con.execute(
            NOTE_SELECT + " WHERE n.verse_ref = ? ORDER BY n.updated_at DESC",
            [str(parsed)],
        ).fetchall()
        return {"notes": [note_row(r) for r in rows]}

    match = search.build_match(q)
    if match:
        rows = con.execute(
            NOTE_SELECT
            + """ WHERE n.id IN (SELECT rowid FROM notes_fts WHERE notes_fts MATCH ?)
                  ORDER BY n.updated_at DESC LIMIT ?""",
            [match, limit],
        ).fetchall()
    else:
        rows = con.execute(
            NOTE_SELECT + " ORDER BY n.updated_at DESC LIMIT ?", [limit]
        ).fetchall()
    return {"notes": [note_row(r) for r in rows]}


@app.post("/api/notes", status_code=201)
def create_note(note: NoteIn, con: sqlite3.Connection = Depends(get_db)):
    parsed = refs.parse(note.verse_ref)
    if parsed is None or not parsed.verse_start:
        raise HTTPException(400, "expected a reference like PHP.4.6")
    if not note.body.strip():
        raise HTTPException(400, "note body is empty")
    # A note remembers which translation was on screen; storing a code that is
    # not in the database would leave it with no verse text to show.
    translation = note.translation
    if translation is not None:
        translation = check_translation(con, translation)
        if translation == "ALL":
            raise HTTPException(400, "a note records one translation, not ALL")
    exists = con.execute(
        "SELECT 1 FROM verses WHERE book = ? AND chapter = ? AND verse = ?",
        [parsed.book, parsed.chapter, parsed.verse_start],
    ).fetchone()
    if not exists:
        raise HTTPException(404, f"no such verse: {note.verse_ref}")

    cur = con.execute(
        """INSERT INTO notes(verse_ref, book, chapter, verse, translation, body)
           VALUES (?,?,?,?,?,?)""",
        [
            str(parsed),
            parsed.book,
            parsed.chapter,
            parsed.verse_start,
            translation,
            note.body.strip(),
        ],
    )
    con.commit()
    row = con.execute(NOTE_SELECT + " WHERE n.id = ?", [cur.lastrowid]).fetchone()
    return note_row(row)


@app.patch("/api/notes/{note_id}")
def update_note(
    note_id: int, patch: NotePatch, con: sqlite3.Connection = Depends(get_db)
):
    if not patch.body.strip():
        raise HTTPException(400, "note body is empty")
    cur = con.execute(
        "UPDATE notes SET body = ?, updated_at = datetime('now') WHERE id = ?",
        [patch.body.strip(), note_id],
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "note not found")
    con.commit()
    row = con.execute(NOTE_SELECT + " WHERE n.id = ?", [note_id]).fetchone()
    return note_row(row)


@app.delete("/api/notes/{note_id}", status_code=204)
def delete_note(note_id: int, con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute("DELETE FROM notes WHERE id = ?", [note_id])
    if cur.rowcount == 0:
        raise HTTPException(404, "note not found")
    con.commit()


@app.get("/api/health")
def health(con: sqlite3.Connection = Depends(get_db)):
    """Liveness only. Cheap enough to poll every few seconds."""
    con.execute("SELECT 1").fetchone()
    return {"ok": True}


@app.get("/api/stats")
def stats(con: sqlite3.Connection = Depends(get_db)):
    """Row counts. Scans three tables, so it is not the thing to poll."""
    return {
        "verses": con.execute("SELECT count(*) FROM verses").fetchone()[0],
        "topics": con.execute("SELECT count(*) FROM topics").fetchone()[0],
        "notes": con.execute("SELECT count(*) FROM notes").fetchone()[0],
        "threads": con.execute("SELECT count(*) FROM study_threads").fetchone()[0],
    }


# --------------------------------------------------------------------------
# highlights
# --------------------------------------------------------------------------

class HighlightIn(BaseModel):
    verse_ref: str = Field(..., examples=["PHP.4.6"])


def highlight_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "verse_ref": r["verse_ref"],
        "book": r["book"],
        "book_name": r["book_name"],
        "chapter": r["chapter"],
        "verse": r["verse"],
        "created_at": r["created_at"],
        "label": refs.label(
            r["book_name"], refs.Ref(r["book"], r["chapter"], r["verse"], r["verse"])
        ),
    }


HIGHLIGHT_SELECT = """
    SELECT h.*, b.name AS book_name FROM highlights h JOIN books b ON b.code = h.book
"""


@app.get("/api/highlights")
def list_highlights(
    ref: str = Query(""),
    limit: int = Query(200, ge=1, le=500),
    con: sqlite3.Connection = Depends(get_db),
):
    if ref:
        parsed = refs.parse(ref)
        if parsed is None:
            raise HTTPException(400, "bad reference")
        rows = con.execute(
            HIGHLIGHT_SELECT + " WHERE h.verse_ref = ?", [str(parsed)]
        ).fetchall()
        return {"highlights": [highlight_row(r) for r in rows]}
    rows = con.execute(
        HIGHLIGHT_SELECT + " ORDER BY h.created_at DESC LIMIT ?", [limit]
    ).fetchall()
    return {"highlights": [highlight_row(r) for r in rows]}


@app.post("/api/highlights", status_code=201)
def create_highlight(body: HighlightIn, con: sqlite3.Connection = Depends(get_db)):
    parsed = refs.parse(body.verse_ref)
    # A highlight marks one verse. A range would store verse_ref="PHP.4.6-7"
    # against verse=6 alone -- DELETE /api/highlights/PHP.4.6 could never
    # address it, and PHP.4.6 and PHP.4.6-7 would collide oddly against the
    # UNIQUE(verse_ref) constraint despite naming overlapping verses.
    if parsed is None or not parsed.verse_start or parsed.verse_end != parsed.verse_start:
        raise HTTPException(400, "expected a single verse, like PHP.4.6")
    exists = con.execute(
        "SELECT 1 FROM verses WHERE book = ? AND chapter = ? AND verse = ?",
        [parsed.book, parsed.chapter, parsed.verse_start],
    ).fetchone()
    if not exists:
        raise HTTPException(404, f"no such verse: {body.verse_ref}")
    con.execute(
        """INSERT INTO highlights(verse_ref, book, chapter, verse) VALUES (?,?,?,?)
           ON CONFLICT(verse_ref) DO NOTHING""",
        [str(parsed), parsed.book, parsed.chapter, parsed.verse_start],
    )
    con.commit()
    row = con.execute(HIGHLIGHT_SELECT + " WHERE h.verse_ref = ?", [str(parsed)]).fetchone()
    return highlight_row(row)


@app.delete("/api/highlights/{verse_ref}", status_code=204)
def delete_highlight(verse_ref: str, con: sqlite3.Connection = Depends(get_db)):
    parsed = refs.parse(verse_ref)
    if parsed is None:
        raise HTTPException(400, "bad reference")
    con.execute("DELETE FROM highlights WHERE verse_ref = ?", [str(parsed)])
    con.commit()


# --------------------------------------------------------------------------
# study threads
# --------------------------------------------------------------------------
#
# The one new primitive: a named collection of verses, each with an optional
# short annotation, that a user builds while reading. Notes stay flat and
# verse-scoped; a thread is what ties several of them together into
# something worth returning to.

class ThreadIn(BaseModel):
    name: str


class ThreadPatch(BaseModel):
    name: str


class ThreadItemIn(BaseModel):
    verse_ref: str = Field(..., examples=["JHN.1.5"])
    note: str | None = None


class ThreadItemPatch(BaseModel):
    note: str


def thread_row(con: sqlite3.Connection, r: sqlite3.Row) -> dict:
    counts = con.execute(
        """SELECT count(*), count(note) FROM thread_items WHERE thread_id = ?""",
        [r["id"]],
    ).fetchone()
    return {
        "id": r["id"],
        "name": r["name"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "item_count": counts[0],
        "note_count": counts[1],
    }


def thread_item_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "thread_id": r["thread_id"],
        "ref": r["verse_ref"],
        "book": r["book"],
        "book_name": r["book_name"],
        "chapter": r["chapter"],
        "verse_start": r["verse_start"],
        "verse_end": r["verse_end"],
        "label": refs.label(
            r["book_name"],
            refs.Ref(r["book"], r["chapter"], r["verse_start"], r["verse_end"]),
        ),
        "note": r["note"],
        "text": r["text"],
    }


THREAD_ITEM_SELECT = """
    SELECT ti.*, b.name AS book_name,
           (SELECT v.text FROM verses v
             WHERE v.translation = ? AND v.book = ti.book AND v.chapter = ti.chapter
               AND v.verse = CASE WHEN ti.verse_start = 0 THEN 1 ELSE ti.verse_start END)
             AS text
    FROM thread_items ti JOIN books b ON b.code = ti.book
"""


@app.get("/api/threads")
def list_threads(
    ref: str = Query(""),
    con: sqlite3.Connection = Depends(get_db),
):
    """Every thread, most recently touched first.

    With `ref`, each thread also carries `contains`: whether that verse is
    already one of its items -- what "Add to thread" needs to show which
    threads a verse already belongs to.
    """
    rows = con.execute(
        "SELECT * FROM study_threads ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    threads = [thread_row(con, r) for r in rows]
    if ref:
        parsed = refs.parse(ref)
        if parsed is None:
            raise HTTPException(400, "bad reference")
        member_of = {
            row[0]
            for row in con.execute(
                "SELECT thread_id FROM thread_items WHERE verse_ref = ?", [str(parsed)]
            )
        }
        for t in threads:
            t["contains"] = t["id"] in member_of
    return {"threads": threads}


@app.post("/api/threads", status_code=201)
def create_thread(body: ThreadIn, con: sqlite3.Connection = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "thread name is empty")
    cur = con.execute(
        "INSERT INTO study_threads(name) VALUES (?)", [body.name.strip()]
    )
    con.commit()
    row = con.execute(
        "SELECT * FROM study_threads WHERE id = ?", [cur.lastrowid]
    ).fetchone()
    return thread_row(con, row)


@app.get("/api/threads/{thread_id}")
def get_thread(
    thread_id: int,
    translation: str = Query("KJV"),
    con: sqlite3.Connection = Depends(get_db),
):
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    row = con.execute(
        "SELECT * FROM study_threads WHERE id = ?", [thread_id]
    ).fetchone()
    if row is None:
        raise HTTPException(404, "thread not found")
    items = con.execute(
        THREAD_ITEM_SELECT + " WHERE ti.thread_id = ? ORDER BY ti.seq",
        [translation, thread_id],
    ).fetchall()
    out = thread_row(con, row)
    out["items"] = [thread_item_row(r) for r in items]
    return out


@app.patch("/api/threads/{thread_id}")
def rename_thread(
    thread_id: int, body: ThreadPatch, con: sqlite3.Connection = Depends(get_db)
):
    if not body.name.strip():
        raise HTTPException(400, "thread name is empty")
    cur = con.execute(
        "UPDATE study_threads SET name = ?, updated_at = datetime('now') WHERE id = ?",
        [body.name.strip(), thread_id],
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "thread not found")
    con.commit()
    row = con.execute(
        "SELECT * FROM study_threads WHERE id = ?", [thread_id]
    ).fetchone()
    return thread_row(con, row)


@app.delete("/api/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: int, con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute("DELETE FROM study_threads WHERE id = ?", [thread_id])
    if cur.rowcount == 0:
        raise HTTPException(404, "thread not found")
    con.commit()


@app.post("/api/threads/{thread_id}/items", status_code=201)
def add_thread_item(
    thread_id: int, body: ThreadItemIn, con: sqlite3.Connection = Depends(get_db)
):
    thread = con.execute(
        "SELECT 1 FROM study_threads WHERE id = ?", [thread_id]
    ).fetchone()
    if thread is None:
        raise HTTPException(404, "thread not found")
    parsed = refs.parse(body.verse_ref)
    if parsed is None or not parsed.verse_start:
        raise HTTPException(400, "expected a reference like PHP.4.6")
    exists = con.execute(
        "SELECT 1 FROM verses WHERE book = ? AND chapter = ? AND verse = ?",
        [parsed.book, parsed.chapter, parsed.verse_start],
    ).fetchone()
    if not exists:
        raise HTTPException(404, f"no such verse: {body.verse_ref}")
    dup = con.execute(
        "SELECT id FROM thread_items WHERE thread_id = ? AND verse_ref = ?",
        [thread_id, str(parsed)],
    ).fetchone()
    if dup is not None:
        raise HTTPException(409, "verse is already in this thread")
    seq = (
        con.execute(
            "SELECT coalesce(max(seq), 0) + 1 FROM thread_items WHERE thread_id = ?",
            [thread_id],
        ).fetchone()[0]
    )
    note = body.note.strip() if body.note and body.note.strip() else None
    cur = con.execute(
        """INSERT INTO thread_items(thread_id, verse_ref, book, chapter, verse_start,
                                     verse_end, note, seq)
           VALUES (?,?,?,?,?,?,?,?)""",
        [
            thread_id,
            str(parsed),
            parsed.book,
            parsed.chapter,
            parsed.verse_start,
            parsed.verse_end,
            note,
            seq,
        ],
    )
    con.commit()
    row = con.execute(
        THREAD_ITEM_SELECT + " WHERE ti.id = ?", ["KJV", cur.lastrowid]
    ).fetchone()
    return thread_item_row(row)


@app.patch("/api/threads/items/{item_id}")
def update_thread_item(
    item_id: int, body: ThreadItemPatch, con: sqlite3.Connection = Depends(get_db)
):
    note = body.note.strip() or None
    cur = con.execute(
        "UPDATE thread_items SET note = ? WHERE id = ?", [note, item_id]
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "thread item not found")
    con.commit()
    row = con.execute(
        THREAD_ITEM_SELECT + " WHERE ti.id = ?", ["KJV", item_id]
    ).fetchone()
    return thread_item_row(row)


@app.delete("/api/threads/items/{item_id}", status_code=204)
def delete_thread_item(item_id: int, con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute("DELETE FROM thread_items WHERE id = ?", [item_id])
    if cur.rowcount == 0:
        raise HTTPException(404, "thread item not found")
    con.commit()


# --------------------------------------------------------------------------
# today
# --------------------------------------------------------------------------

# A small, deliberately-picked set -- not a random verse from all 31,102,
# which would as often land on a genealogy or a building measurement as
# anything worth opening the app to read.
VERSE_OF_THE_DAY_POOL = [
    "JHN.1.1", "JHN.1.5", "JHN.3.16", "JHN.8.12", "JHN.15.5",
    "PSA.23.1", "PSA.46.1", "PSA.100.5", "PSA.119.105", "PSA.139.14",
    "PRO.3.5-6", "ISA.40.31", "ISA.41.10", "ISA.43.2",
    "MAT.5.14", "MAT.6.33", "MAT.11.28",
    "ROM.8.28", "ROM.12.2", "1CO.13.4-7", "2CO.5.17",
    "GAL.5.22-23", "EPH.2.8-9", "PHP.4.6-7", "PHP.4.13",
    "COL.3.23", "1TH.5.16-18", "HEB.11.1", "HEB.12.1",
    "JAS.1.2-4", "1PE.5.7", "1JN.4.19", "REV.21.4",
]


@app.get("/api/today")
def today(translation: str = Query("KJV"), con: sqlite3.Connection = Depends(get_db)):
    """One verse, and the thread most recently worked on.

    The verse is picked deterministically from the day of the year, not at
    random and not from any server -- the same date always lands on the same
    verse, offline, which is what makes it safe to prefetch and to show the
    same thing if the app is opened twice in one day.
    """
    translation = check_translation(con, translation)
    if translation == "ALL":
        translation = "KJV"
    day = datetime.date.today().timetuple().tm_yday
    ref = VERSE_OF_THE_DAY_POOL[day % len(VERSE_OF_THE_DAY_POOL)]
    parsed = refs.parse(ref)
    # A pool entry can be a range (PHP.4.6-7): fetch every verse in it and
    # join the text, so the card's text actually matches the range its own
    # label names instead of showing just the first verse under a heading
    # that promises more.
    rows = con.execute(
        """SELECT v.id, v.book, v.chapter, v.verse, v.translation, v.text,
                  b.name AS book_name
           FROM verses v JOIN books b ON b.code = v.book
           WHERE v.book = ? AND v.chapter = ? AND v.verse BETWEEN ? AND ?
             AND v.translation = ?
           ORDER BY v.verse""",
        [parsed.book, parsed.chapter, parsed.verse_start, parsed.verse_end, translation],
    ).fetchall()

    verse = None
    if rows:
        verse = verse_row(rows[0])
        verse["text"] = " ".join(r["text"] for r in rows)

    recent_thread = con.execute(
        "SELECT * FROM study_threads ORDER BY updated_at DESC, id DESC LIMIT 1"
    ).fetchone()

    return {
        "verse_of_day": {
            "ref": str(parsed),
            "label": refs.label(rows[0]["book_name"], parsed) if rows else ref,
            "verse": verse,
        },
        "recent_thread": thread_row(con, recent_thread) if recent_thread else None,
    }


# --------------------------------------------------------------------------
# static SPA (mounted last so /api/* wins)
# --------------------------------------------------------------------------

DIST = (Path(__file__).resolve().parent.parent / "web" / "dist").resolve()

if DIST.exists():
    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        index = DIST / "index.html"
        # An unmatched /api/... is a missing endpoint, not a page. Handing back
        # index.html would turn a typo into a 200 full of HTML.
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        if not path:
            return FileResponse(index)
        candidate = (DIST / path).resolve()
        # `..` in the request must not walk out of the build directory.
        if candidate.is_file() and candidate.is_relative_to(DIST):
            return FileResponse(candidate)
        return FileResponse(index)
