"""Concordance API.

Read-only scripture + Nave's topical index out of SQLite/FTS5, plus personal
notes that live in the same database. Nothing here talks to the network; the
translations were pulled once at setup by etl/fetch_sources.py.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, refs, search

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
    include: str = Query("verses,topics,notes"),
    con: sqlite3.Connection = Depends(get_db),
):
    """Full-text search over verses, Nave's topic names and personal notes."""
    translation = check_translation(con, translation)
    match = search.build_match(q)
    wanted = {p.strip() for p in include.split(",")}
    empty = {
        "query": q,
        "translation": translation,
        "verses": [],
        "verse_total": 0,
        "topics": [],
        "notes": [],
    }
    if not match:
        return empty

    result = dict(empty)

    if "verses" in wanted:
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
        result["verse_total"] = con.execute(
            f"""SELECT count(*) FROM verses_fts
                JOIN verses v ON v.id = verses_fts.rowid
                WHERE {where}""",
            params,
        ).fetchone()[0]

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
    verses = []
    for r in rows:
        v = verse_row(r)
        v["note_count"] = noted.get(r["verse"], 0)
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
                        "text": s["text"],
                    }
                    for s in siblings
                ],
            }
        )
    return {"ref": str(parsed), "translation": translation, "topics": out}


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
