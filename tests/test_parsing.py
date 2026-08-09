"""Parsing rules that are easy to get wrong and expensive to notice later."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "etl"))

from etl import build_db  # noqa: E402
from etl import books as bk  # noqa: E402
from server import refs, search  # noqa: E402


class BookCodes(unittest.TestCase):
    def test_canonical_set(self):
        self.assertEqual(len(bk.CODES), 66)
        self.assertEqual(bk.ORDINAL["GEN"], 1)
        self.assertEqual(bk.ORDINAL["REV"], 66)

    def test_resolves_names_and_codes(self):
        self.assertEqual(bk.resolve("Philippians"), "PHP")
        self.assertEqual(bk.resolve("PHP"), "PHP")
        self.assertEqual(bk.resolve("1 Samuel"), "1SA")
        self.assertEqual(bk.resolve("I Samuel"), "1SA")
        self.assertEqual(bk.resolve("Song of Songs"), "SNG")
        self.assertIsNone(bk.resolve("Maccabees"))

    def test_fixes_source_typos(self):
        # Nave's contains one "1JHN" among 76k references.
        self.assertEqual(bk.resolve("1JHN"), "1JN")


class NaveReferences(unittest.TestCase):
    def parse(self, line):
        return list(build_db.parse_nave_line(line))

    def test_range_and_list(self):
        self.assertEqual(
            self.parse("-Lineage of EXO 6:16-20; JOS 21:4,10"),
            [("EXO", 6, 16, 20), ("JOS", 21, 4, 4), ("JOS", 21, 10, 10)],
        )

    def test_book_carries_across_semicolons(self):
        # "23:13" belongs to 1CH, the last book code seen.
        self.assertEqual(
            self.parse("-Children of 1CH 6:3; 23:13"),
            [("1CH", 6, 3, 3), ("1CH", 23, 13, 13)],
        )

    def test_whole_chapter_reference(self):
        # verse 0 marks a reference to the entire chapter.
        self.assertEqual(self.parse("-Priesthood of NUM 17"), [("NUM", 17, 0, 0)])

    def test_numbers_before_any_book_are_prose(self):
        self.assertEqual(self.parse("-The 12 tribes"), [])

    def test_ref_formatting(self):
        self.assertEqual(build_db.format_ref("PHP", 4, 6, 7), "PHP.4.6-7")
        self.assertEqual(build_db.format_ref("PHP", 4, 6, 6), "PHP.4.6")
        self.assertEqual(build_db.format_ref("NUM", 17, 0, 0), "NUM.17")


class CallNumbers(unittest.TestCase):
    def test_round_trip(self):
        for text in ("PHP.4.6", "PHP.4.6-7", "1CH.23"):
            self.assertEqual(str(refs.parse(text)), text)

    def test_rejects_junk(self):
        for text in (
            "",
            "PHP",
            "PHP.4.6.5",
            "../../etc/passwd",
            "PHP.four.6",
            # too many digits to be a chapter, and too large for SQLite to bind
            "PHP.99999999999999999999.1",
            "PHP.1234.1",
            "PHP.٤.٦",  # Arabic-Indic digits are not references
        ):
            self.assertIsNone(refs.parse(text), text)

    def test_labels(self):
        self.assertEqual(
            refs.label("Philippians", refs.Ref("PHP", 4, 6, 7)), "Philippians 4:6-7"
        )
        self.assertEqual(refs.label("Numbers", refs.Ref("NUM", 17, 0, 0)), "Numbers 17")


class SearchQueries(unittest.TestCase):
    def test_terms_are_quoted_so_operators_are_inert(self):
        self.assertEqual(search.build_match("peace AND war"), '"peace" AND "AND" AND "war" *')

    def test_phrases_survive(self):
        self.assertEqual(
            search.build_match('"still waters" green', prefix_last=False),
            '"still waters" AND "green"',
        )

    def test_prefix_only_on_the_last_term(self):
        self.assertEqual(search.build_match("good shep"), '"good" AND "shep" *')

    def test_unstemmed_index_prefixes_sooner(self):
        # Topic names are matched on a raw index, where short prefixes are safe.
        self.assertEqual(search.build_match("pr", stem=False), '"pr" *')
        self.assertEqual(search.build_match("pr", stem=True), '"pr"')

    def test_punctuation_only_input_is_not_a_query(self):
        for junk in ("", "   ", '"', "-", "*", "()"):
            self.assertIsNone(search.build_match(junk), junk)

    def test_highlight_segments(self):
        marked = f"a {search.MARK_OPEN}hit{search.MARK_CLOSE} b"
        self.assertEqual(
            search.split_marks(marked),
            [{"text": "a ", "hit": False}, {"text": "hit", "hit": True}, {"text": " b", "hit": False}],
        )


if __name__ == "__main__":
    unittest.main()
