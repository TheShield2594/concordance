"""The original-language layer: interlinear verses and Strong's lookup.

`original_words` holds one row per word of the Hebrew, Aramaic or Greek, in the
order it stands in its verse. Nothing here writes, and nothing here goes near
FTS5 -- a Strong's number is an exact key, so the concordance is an index scan.
"""
from __future__ import annotations

import re
import sqlite3

LANGUAGES = {
    "heb": ("Hebrew", "rtl"),
    "arc": ("Aramaic", "rtl"),
    "grc": ("Greek", "ltr"),
}

# H2617, g26, "H 0430" -- and the disambiguating letter STEPBible adds to a
# number that covers more than one word (H1254A) is dropped, because the
# dictionary knows nothing about it.
STRONGS_QUERY = re.compile(r"^\s*([HhGg])\s*0*(\d{1,4})\s*[A-Za-z]?\s*$")


def parse_strongs(value: str) -> str | None:
    """Normalise anything the user might type into a dictionary key: 'H430'."""
    m = STRONGS_QUERY.match(value or "")
    if not m:
        return None
    return f"{m.group(1).upper()}{int(m.group(2))}"


def word_row(r: sqlite3.Row) -> dict:
    return {
        # `verse` and `seq` together identify the word: a Psalm title is verse
        # 0 and numbers its own words from 1, so it collides with verse 1 on
        # seq alone.
        "verse": r["verse"],
        "seq": r["seq"],
        "lang": r["lang"],
        "surface": r["surface"],
        "translit": r["translit"],
        "gloss": r["gloss"],
        "strongs": r["strongs"],
        "strongs_base": r["strongs_base"],
        "morph": r["morph"],
        "parsing": r["parsing"],
        "lemma": r["lemma"],
        "lemma_gloss": r["lemma_gloss"],
        "editions": r["editions"],
        "variant": bool(r["variant"]),
        # Prefixes and suffixes are tagged H9xxx, which is STEPBible's own
        # extension: real words to show, but Strong's never numbered them, so
        # there is nothing to open.
        "in_dictionary": bool(r["in_dictionary"]),
    }


WORD_SELECT = """
    SELECT w.verse, w.seq, w.lang, w.surface, w.translit, w.gloss, w.strongs,
           w.strongs_base, w.morph, w.parsing, w.lemma, w.lemma_gloss,
           w.editions, w.variant,
           (s.id IS NOT NULL) AS in_dictionary
    FROM original_words w
    LEFT JOIN strongs_entries s ON s.id = w.strongs_base
"""


def words_for(
    con: sqlite3.Connection, book: str, chapter: int, verse: int
) -> list[sqlite3.Row]:
    """The original of one verse, superscription included where there is one.

    A Psalm title is verse 1 in Hebrew and unnumbered in English, so the ETL
    files it as verse 0. It belongs at the head of verse 1 and nowhere else.
    """
    verses = [verse]
    if verse == 1:
        verses.append(0)
    marks = ",".join("?" * len(verses))
    return con.execute(
        WORD_SELECT
        + f" WHERE w.book = ? AND w.chapter = ? AND w.verse IN ({marks})"
        " ORDER BY w.verse = 0 DESC, w.seq",
        [book, chapter, *verses],
    ).fetchall()


def entry_row(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "lang": r["lang"],
        "language": LANGUAGES[r["lang"]][0],
        "direction": LANGUAGES[r["lang"]][1],
        "lemma": r["lemma"],
        "translit": r["translit"],
        "pron": r["pron"],
        "derivation": r["derivation"],
        "definition": r["definition"],
        "kjv_usage": r["kjv_usage"],
    }
