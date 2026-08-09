"""Call-number references: PHP.4.6 and PHP.4.6-7."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Digits are capped at three and restricted to ASCII: no book runs past Psalm
# 150 or verse 176, and an unbounded \d also matches other scripts' digits and
# integers too large for SQLite to bind.
REF_RE = re.compile(
    r"^\s*([1-3]?[A-Za-z]{2,3})\.([0-9]{1,3})(?:\.([0-9]{1,3})(?:-([0-9]{1,3}))?)?\s*$"
)


@dataclass(frozen=True)
class Ref:
    book: str
    chapter: int
    verse_start: int  # 0 == whole chapter
    verse_end: int

    def __str__(self) -> str:
        if not self.verse_start:
            return f"{self.book}.{self.chapter}"
        if self.verse_end > self.verse_start:
            return f"{self.book}.{self.chapter}.{self.verse_start}-{self.verse_end}"
        return f"{self.book}.{self.chapter}.{self.verse_start}"


def parse(ref: str) -> Ref | None:
    m = REF_RE.match(ref or "")
    if not m:
        return None
    book, chapter, start, end = m.groups()
    start_i = int(start) if start else 0
    return Ref(book.upper(), int(chapter), start_i, int(end) if end else start_i)


def label(book_name: str, ref: Ref) -> str:
    """Human-readable form for a reference, e.g. 'Philippians 4:6-7'."""
    if not ref.verse_start:
        return f"{book_name} {ref.chapter}"
    if ref.verse_end > ref.verse_start:
        return f"{book_name} {ref.chapter}:{ref.verse_start}-{ref.verse_end}"
    return f"{book_name} {ref.chapter}:{ref.verse_start}"
