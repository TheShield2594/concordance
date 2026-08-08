"""Turning what someone types into an FTS5 query they can't break.

Raw input goes straight into `MATCH`, where a stray quote or a bare `-` is a
syntax error and `AND`/`NEAR` are operators. So the input is tokenised and
re-emitted as quoted terms: whatever is typed is treated as literal words.
"""
from __future__ import annotations

import re

# Highlight markers. Private-use codepoints, so they can never collide with
# scripture text; the client splits on them to render <mark> spans.
MARK_OPEN = ""
MARK_CLOSE = ""

# "quoted phrases" stay intact; everything else splits on non-word characters.
_PHRASE = re.compile(r'"([^"]+)"')
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def parse_terms(query: str) -> list[str]:
    """Split user input into phrases and words, preserving "quoted phrases"."""
    terms: list[str] = []
    rest = query or ""
    for phrase in _PHRASE.findall(rest):
        words = _WORD.findall(phrase)
        if words:
            terms.append(" ".join(words))
    rest = _PHRASE.sub(" ", rest)
    terms.extend(_WORD.findall(rest))
    return [t for t in terms if t]


def build_match(query: str, prefix_last: bool = True, stem: bool = True) -> str | None:
    """Build an FTS5 MATCH expression, or None if there is nothing to search.

    The final term gets a `*` so results appear while still typing ("righteo"
    matches "righteousness"). Every term is quoted, so operators and
    punctuation are inert.

    `stem` says whether the target index uses the porter tokenizer. On a stemmed
    index a short prefix is rewritten before it is matched ("pray" -> "prai*"),
    so prefixing is held back until there is enough of a word to be useful.
    """
    terms = parse_terms(query)
    if not terms:
        return None
    min_prefix = 3 if stem else 1
    parts = []
    for i, term in enumerate(terms):
        last = i == len(terms) - 1
        quoted = '"' + term.replace('"', "") + '"'
        if last and prefix_last and " " not in term and len(term) >= min_prefix:
            quoted += " *"  # FTS5 prefix syntax: "term" *
        parts.append(quoted)
    return " AND ".join(parts)


def split_marks(text: str) -> list[dict]:
    """Turn marker-delimited text into [{text, hit}] segments for the client."""
    segments: list[dict] = []
    for chunk in re.split(f"({MARK_OPEN}[^{MARK_CLOSE}]*{MARK_CLOSE})", text):
        if not chunk:
            continue
        if chunk.startswith(MARK_OPEN):
            segments.append({"text": chunk[1:-1], "hit": True})
        else:
            segments.append({"text": chunk, "hit": False})
    return segments
