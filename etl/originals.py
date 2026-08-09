"""Parse the tagged Hebrew/Aramaic/Greek text and Strong's dictionaries.

Two shapes of source, both public and both pinned by fetch_sources.py:

  STEPBible TAHOT/TAGNT   one tab-separated line per word of the original,
                          carrying the word, a transliteration, the sense it
                          takes in this verse, a Strong's number and a
                          morphology code.  CC BY 4.0.
  openscriptures/strongs  Strong's own dictionary entries, as a JavaScript
                          file with a JSON object inside it.

The two STEPBible corpora do not share a column layout, so they get a parser
each; both hand back the same `Word`.

Nothing here needs the network -- fetch_sources.py has already put the files
in data/sources.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import books as bk  # noqa: E402

# Hebrew and Aramaic OT, then Greek NT. The split into four/two files is
# upstream's, purely to keep each one under a sensible size.
TAHOT_FILES = [
    "TAHOT-Gen-Deu.txt",
    "TAHOT-Jos-Est.txt",
    "TAHOT-Job-Sng.txt",
    "TAHOT-Isa-Mal.txt",
]
TAGNT_FILES = ["TAGNT-Mat-Jhn.txt", "TAGNT-Act-Rev.txt"]

MORPH_FILES = {"heb": "TEHMC.txt", "grc": "TEGMC.txt"}
STRONGS_FILES = {
    "heb": ("strongs-hebrew-dictionary.js", "H"),
    "grc": ("strongs-greek-dictionary.js", "G"),
}


@dataclass(frozen=True)
class Word:
    """One word of the original text, in the place it stands in a verse."""

    book: str
    chapter: int
    verse: int          # 0 == a Psalm superscription, unnumbered in English
    seq: int
    lang: str           # heb | arc | grc
    surface: str        # the word as it is written
    translit: str
    gloss: str          # what it means *here*, from the taggers
    strongs: str        # disambiguated: H4428G, H9005
    strongs_base: str   # what the dictionary is keyed by: H4428
    morph: str          # raw morphology code
    parsing: str        # that code in words, via TEHMC/TEGMC
    lemma: str          # dictionary form
    lemma_gloss: str    # its general sense, as against `gloss`
    editions: str       # which editions carry the word (Greek), text type (Hebrew)
    variant: int        # 1 when no critical edition carries it


# Gen.1.1#01=L, Psa.3.1(Psa.3.2)#04=L, Mat.15.6{15.5}#01=k
WORD_REF = re.compile(
    r"^([0-9A-Za-z]{2,4})\.(\d+)\.(\d+)"      # English reference
    r"(?:[({][^)}]*[)}])?"                    # the Hebrew/alternative one, ignored
    r"#(\d+)(?:\.(\d+))?"                     # word number, occasionally split
    r"(?:=(\S+))?$"                           # text type / editions
)

# H0430G -> H0430; the trailing letter is STEPBible disambiguating a Strong's
# number that covers more than one word. The dictionaries are keyed without it,
# and without the zero padding.
STRONGS_TAG = re.compile(r"([HG])0*(\d+)([A-Za-z]*)")


def normalise_strongs(tag: str) -> tuple[str, str]:
    """('{H0430G}') -> ('H430G', 'H430'). Empty strings when there is no number."""
    m = STRONGS_TAG.search(tag or "")
    if not m:
        return "", ""
    letter, number, suffix = m.groups()
    return f"{letter}{number}{suffix.upper()}", f"{letter}{number}"


def pick_main(segments: list[str]) -> int:
    """Which morpheme of a Hebrew word is the word itself, rather than an affix.

    The taggers brace it: `H9005/{H4428G}` is "to the" + "king", and it is the
    king we want the dictionary entry for. Without braces (Greek, and Hebrew
    words that stand alone) there is only ever one segment.
    """
    for i, seg in enumerate(segments):
        if "{" in seg:
            return i
    return len(segments) - 1 if segments else 0


def prettify_parsing(expansion: str) -> str:
    """'Function=Noun; Number=Plural' -> 'Noun · Plural'."""
    # The Hebrew table glosses its own codes in brackets -- "Qal (hence
    # Action=Simple; Voice=Active)" -- and those brackets carry the semicolons
    # and equals signs this splits on. Drop them before parsing, not after.
    expansion = re.sub(r"\([^)]*\)", "", expansion or "")
    parts = []
    for chunk in expansion.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        value = chunk.split("=", 1)[1].strip() if "=" in chunk else chunk
        if value:
            parts.append(value)
    return " · ".join(parts)


def load_morphology(path: Path) -> dict[str, str]:
    """code -> parsing in words, from a TEHMC/TEGMC table."""
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if "\t" not in line:
            continue
        code, expansion = line.split("\t", 1)
        code = code.strip()
        # Data rows are `CODE<TAB>Function=...`; the prose above them is not.
        if not code or " " in code or "=" not in expansion:
            continue
        table.setdefault(code, prettify_parsing(expansion.split("\t")[0]))
    return table


def load_strongs(path: Path, lang: str, letter: str):
    """Yield dictionary entries from openscriptures' JavaScript-wrapped JSON."""
    text = path.read_text(encoding="utf-8")
    blob = text[text.index("{"): text.rindex("}") + 1]
    for key, entry in json.loads(blob).items():
        _, base = normalise_strongs(key)
        if not base or not base.startswith(letter):
            continue
        yield (
            base,
            lang,
            _nfc(entry.get("lemma", "")),
            entry.get("translit") or entry.get("xlit", ""),
            entry.get("pron", ""),
            (entry.get("derivation") or "").strip(),
            (entry.get("strongs_def") or "").strip(),
            (entry.get("kjv_def") or "").strip(),
        )


def _clean(value: str) -> str:
    """Drop the morpheme dividers and tidy the spacing they leave behind."""
    return re.sub(r"\s+", " ", (value or "").replace("/", " ")).strip()


def _nfc(value: str) -> str:
    """Compose the text the standard way.

    The Greek arrives using the oxia accents (U+1F79) rather than the tonos
    ones (U+03CC). The two are canonically equivalent, so they look identical
    and compare unequal, which is the worst of both. NFC settles it, and takes
    the Hebrew points into canonical order while it is there.
    """
    return unicodedata.normalize("NFC", value or "")


def parse_tahot(path: Path, morphology: dict[str, str]):
    """Yield Words from a Translators Amalgamated Hebrew OT file.

    Columns: reference, Hebrew, transliteration, translation, dStrongs,
    grammar, ... , expanded Strong tags.
    """
    seqs: dict[tuple[str, int, int], int] = {}
    for row in _rows(path, 12):
        ref = _parse_ref(row[0])
        if ref is None:
            continue
        book, chapter, verse, text_type = ref

        strongs_segments = (row[4] or "").split("/")
        grammar_segments = (row[5] or "").split("/")
        main = pick_main(strongs_segments)

        strongs, base = normalise_strongs(strongs_segments[main])
        morph = grammar_segments[main] if main < len(grammar_segments) else ""
        # Only the first morpheme spells out the language; H = Hebrew, A =
        # Aramaic, and the Aramaic stretches of Daniel and Ezra are the reason
        # this is worth reading rather than assuming.
        head = grammar_segments[0][:1] if grammar_segments and grammar_segments[0] else "H"
        lang = "arc" if head == "A" else "heb"
        # Only the leading morpheme carries the language letter, and a later
        # one can perfectly well start with an A of its own ("Aamsa" is an
        # adjective, not Aramaic), so this goes by position, not by spelling.
        code = morph if main == 0 else head + morph

        lemma, lemma_gloss = _tahot_lemma(row[11], strongs_segments[main])

        key = (book, chapter, verse)
        seqs[key] = seqs.get(key, 0) + 1
        yield Word(
            book=book,
            chapter=chapter,
            verse=verse,
            seq=seqs[key],
            lang=lang,
            surface=_nfc((row[1] or "").replace("/", "")),
            translit=(row[2] or "").replace("/", ""),
            gloss=_clean(row[3]),
            strongs=strongs,
            strongs_base=base,
            # Stored with the leading language letter whichever morpheme it came
            # from, so every Hebrew code in the table reads the same way.
            morph=code,
            parsing=morphology.get(code, ""),
            lemma=_nfc(lemma),
            lemma_gloss=lemma_gloss,
            editions=text_type,
            variant=0,
        )


# H9003=ב=in/{H7225G=רֵאשִׁית=: beginning»first:1_beginning}
#
# One tag per morpheme, run together with slashes -- and both the lemma and the
# sense may contain a slash themselves, so the field is cut at the tags rather
# than split on the separator.
TAHOT_TAG_START = re.compile(r"\{?([HG]\d+[A-Za-z]*)=")


def _tahot_lemma(expanded: str, strongs_segment: str) -> tuple[str, str]:
    """Dig the dictionary form out of the expanded Strong tags column."""
    wanted, _ = normalise_strongs(strongs_segment)
    fallback = ("", "")
    marks = list(TAHOT_TAG_START.finditer(expanded or ""))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(expanded)
        lemma, _, sense = expanded[m.end(): end].partition("=")
        # `beginning»first:1_beginning` -- everything after the arrow is the
        # tagging apparatus, not a gloss anybody wants to read.
        sense = sense.split("»")[0].lstrip(": ").strip().rstrip("}/").strip()
        found = (lemma.strip().rstrip("/"), sense)
        if normalise_strongs(m.group(1))[0] == wanted:
            return found
        if not fallback[0]:
            fallback = found
    return fallback


def parse_tagnt(path: Path, morphology: dict[str, str]):
    """Yield Words from a Translators Amalgamated Greek NT file.

    Columns: reference, Greek, English translation, dStrongs=grammar,
    dictionary form=gloss, editions, ...
    """
    seqs: dict[tuple[str, int, int], int] = {}
    for row in _rows(path, 6):
        ref = _parse_ref(row[0])
        if ref is None:
            continue
        book, chapter, verse, editions = ref

        surface, _, translit = (row[1] or "").partition(" (")
        strongs_raw, _, morph = (row[3] or "").partition("=")
        lemma, _, lemma_gloss = (row[4] or "").partition("=")
        strongs, base = normalise_strongs(strongs_raw)
        # A crasis is tagged as both its parts -- "G2504=P-1NS + G2532=CONJ"
        # for κἀγώ. The first is the word the reader looked up.
        morph = morph.split(" + ")[0]

        # Two statements of which editions carry the word: a terse code on the
        # reference (NKO) and the full list in its own column. Where both are
        # present the list is the fuller one and settles it -- a reference
        # marked "no" means NA28 has the word with a variant spelling, and
        # reading the code alone would file it as Received Text only.
        editions = row[5].strip() or editions

        key = (book, chapter, verse)
        seqs[key] = seqs.get(key, 0) + 1
        yield Word(
            book=book,
            chapter=chapter,
            verse=verse,
            seq=seqs[key],
            lang="grc",
            surface=_nfc(surface.strip()),
            translit=translit.rstrip(")").strip(),
            gloss=_clean(row[2]),
            strongs=strongs,
            strongs_base=base,
            morph=morph.strip(),
            parsing=morphology.get(morph.strip(), ""),
            lemma=_nfc(lemma.strip()),
            lemma_gloss=lemma_gloss.strip(),
            editions=editions,
            # An uppercase N means an edition of the critical text carries the
            # word. Without one it is in the Received Text alone -- which is
            # exactly the KJV's underlying text, so it is shown, and flagged.
            variant=0 if "N" in editions else 1,
        )


def _rows(path: Path, min_columns: int):
    """Yield tab-split data rows, skipping the prose and the repeated headers."""
    with path.open(encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            row = line.rstrip("\n").split("\t")
            if len(row) > min_columns and "." in row[0] and "#" in row[0]:
                yield row


def _parse_ref(field: str) -> tuple[str, int, int, str] | None:
    m = WORD_REF.match(field.strip())
    if not m:
        return None
    code = bk.resolve(m.group(1))
    if code is None:
        return None
    return code, int(m.group(2)), int(m.group(3)), (m.group(6) or "")
