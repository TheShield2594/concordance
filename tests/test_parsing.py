"""Parsing rules that are easy to get wrong and expensive to notice later."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "etl"))

from etl import build_db  # noqa: E402
from etl import books as bk  # noqa: E402
from etl import originals as og  # noqa: E402
from server import originals as sog  # noqa: E402
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

    def test_resolves_the_abbreviations_people_type(self):
        # "Phil" is Philippians by convention, never Philemon (that's Phlm).
        for typed, code in [
            ("Matt", "MAT"), ("Mt", "MAT"), ("Phil", "PHP"), ("Phlm", "PHM"),
            ("1 Thess.", "1TH"), ("Ps", "PSA"), ("Song", "SNG"), ("1 Jn", "1JN"),
        ]:
            self.assertEqual(bk.resolve(typed), code, typed)

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


class HumanReferences(unittest.TestCase):
    def test_typed_forms_come_back_canonical(self):
        for typed, want in [
            ("John 3:16", "JHN.3.16"),
            ("john 3.16", "JHN.3.16"),
            ("Php 4:6", "PHP.4.6"),
            ("Phil 4:6-7", "PHP.4.6-7"),
            ("1 Thess 4:16", "1TH.4.16"),
            ("Psalm 23", "PSA.23"),
            ("Song of Solomon 2:1", "SNG.2.1"),
            ("1 Sam. 17:4", "1SA.17.4"),
            ("matt 5 3", "MAT.5.3"),
            ("rev 21:3–4", "REV.21.3-4"),  # the dash a phone keyboard supplies
            ("PHP.4.6", "PHP.4.6"),  # the call number itself still works
            ("JOH.3.16", "JHN.3.16"),  # and a near-miss code is canonicalised
        ]:
            self.assertEqual(str(refs.parse_human(typed)), want, typed)

    def test_what_only_looks_like_a_reference_is_not_one(self):
        for typed in (
            "",
            "love",
            "john",  # a book with no chapter is a word, not a reference
            "grace 4:6",  # a chapter and verse under a word that names no book
            "the 12 tribes",
            "H2617",  # Strong's numbers keep their own lane
            "G26",
            "3:16",
            "john 3:16-2",  # a range running backwards
            "PHP.99999999999999999999.1",
        ):
            self.assertIsNone(refs.parse_human(typed), typed)


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


class StrongsNumbers(unittest.TestCase):
    def test_normalises_the_padding_and_the_disambiguating_letter(self):
        # STEPBible writes H0430G; the dictionary is keyed H430.
        self.assertEqual(og.normalise_strongs("{H0430G}"), ("H430G", "H430"))
        self.assertEqual(og.normalise_strongs("G1722"), ("G1722", "G1722"))

    def test_no_number_is_not_a_number(self):
        self.assertEqual(og.normalise_strongs(""), ("", ""))
        self.assertEqual(og.normalise_strongs("HR"), ("", ""))

    def test_query_forms_people_actually_type(self):
        for typed in ("H2617", "h2617", " H 2617 ", "H02617", "H2617a"):
            self.assertEqual(sog.parse_strongs(typed), "H2617", typed)
        self.assertEqual(sog.parse_strongs("g26"), "G26")

    def test_ordinary_words_are_not_strongs_numbers(self):
        for typed in ("grace", "", "26", "H", "H99999", "GEN.1.1"):
            self.assertIsNone(sog.parse_strongs(typed), typed)


class TaggedOriginals(unittest.TestCase):
    def test_the_braced_morpheme_is_the_word_itself(self):
        # "to the/king": the affix is tagged too, but the king is the entry.
        self.assertEqual(og.pick_main(["H9005", "{H4428G}"]), 1)
        self.assertEqual(og.pick_main(["{H1254A}"]), 0)
        # No braces at all: the last morpheme carries the sense.
        self.assertEqual(og.pick_main(["H9001", "H1696"]), 1)

    def test_parsing_codes_read_as_english(self):
        self.assertEqual(
            og.prettify_parsing("Function=Noun; Number=Plural"), "Noun · Plural"
        )

    def test_bracketed_glosses_do_not_leak_into_the_parsing(self):
        # The Hebrew table explains its own codes in brackets, and those
        # brackets contain the separators this splits on.
        self.assertEqual(
            og.prettify_parsing(
                "Function=Verb; Stem=Qal (hence Action=Simple; Voice=Active); "
                "Person=Third"
            ),
            "Verb · Qal · Third",
        )

    def test_lemma_comes_from_the_tag_that_matches_the_word(self):
        # Both morphemes are tagged in one field, run together with a slash.
        expanded = "H9003=ב=in/{H7225G=רֵאשִׁית=: beginning»first:1_beginning}"
        self.assertEqual(
            og._tahot_lemma(expanded, "{H7225G}"), ("רֵאשִׁית", "beginning")
        )
        # Asking for the prefix gets the prefix, not the noun beside it.
        self.assertEqual(og._tahot_lemma(expanded, "H9003"), ("ב", "in"))

    def test_the_edition_column_outranks_the_reference_code(self):
        # "=no" says NA has the word with a variant spelling; reading that code
        # alone flags it as Received Text only, which is the opposite of true.
        row = [
            "Mat.3.6#06=no",
            "ποταμῷ (potamō)",
            "river",
            "G4215=N-DSM",
            "ποταμός=river",
            "NA28+NA27+Tyn+SBL+WH+Treg",
            "", "", "", "", "", "", "",
        ]
        word = self._one_tagnt_word(row)
        self.assertEqual(word.variant, 0)
        self.assertEqual(word.editions, "NA28+NA27+Tyn+SBL+WH+Treg")

    def test_the_edition_column_stands_alone_without_a_reference_code(self):
        # Every row in the corpus today carries a code, but the reference
        # grammar makes it optional. With nothing to merge, the column is the
        # only witness -- and reading the empty code would flag the word.
        row = [
            "Mat.3.6#06",
            "ποταμῷ (potamō)",
            "river",
            "G4215=N-DSM",
            "ποταμός=river",
            "NA28+NA27+Tyn+SBL+WH+Treg",
            "", "", "", "", "", "", "",
        ]
        word = self._one_tagnt_word(row)
        self.assertEqual(word.variant, 0)
        self.assertEqual(word.editions, "NA28+NA27+Tyn+SBL+WH+Treg")

    def test_a_received_text_only_word_is_still_flagged(self):
        row = [
            "Mat.15.6#01=k",
            "καὶ (kai)",
            "and",
            "G2532=CONJ",
            "καί=and",
            "TR+Byz",
            "", "", "", "", "", "", "",
        ]
        self.assertEqual(self._one_tagnt_word(row).variant, 1)

    def _one_tagnt_word(self, row):
        """Run one hand-written TAGNT line through the real parser."""
        path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "TAGNT.txt"
        path.write_text("\t".join(row) + "\n", encoding="utf-8")
        words = list(og.parse_tagnt(path, {}))
        self.assertEqual(len(words), 1)
        return words[0]

    def test_reference_forms(self):
        self.assertEqual(og._parse_ref("Gen.1.1#01=L"), ("GEN", 1, 1, "L"))
        # A Hebrew or alternative versification in brackets is not the ref.
        self.assertEqual(og._parse_ref("Psa.3.1(Psa.3.2)#04=L"), ("PSA", 3, 1, "L"))
        self.assertEqual(og._parse_ref("Mat.15.6{15.5}#01=k"), ("MAT", 15, 6, "k"))
        self.assertEqual(og._parse_ref("Jhn.1.1#02=NKO"), ("JHN", 1, 1, "NKO"))
        self.assertIsNone(og._parse_ref("not a reference"))


if __name__ == "__main__":
    unittest.main()
