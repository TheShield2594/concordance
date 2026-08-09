"""End-to-end checks against a real (small) database built by the ETL.

Needs data/concordance.db. Missing it is a failure, not a skip, so a CI job
without the database can't come back green having asserted nothing. Set
CONCORDANCE_ALLOW_SKIP=1 to skip instead, which is what you want locally before
the first `make data`.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import refs  # noqa: E402
from server.search import MARK_OPEN  # noqa: E402

SOURCE_DB = Path(os.environ.get("CONCORDANCE_DB", ROOT / "data" / "concordance.db"))
ALLOW_SKIP = os.environ.get("CONCORDANCE_ALLOW_SKIP") not in (None, "", "0")


@unittest.skipIf(
    ALLOW_SKIP and not SOURCE_DB.exists(),
    f"{SOURCE_DB} not built and CONCORDANCE_ALLOW_SKIP is set",
)
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE_DB.exists():
            raise AssertionError(
                f"{SOURCE_DB} does not exist -- run `make data` first, or set "
                "CONCORDANCE_ALLOW_SKIP=1 to skip these tests"
            )
        # Work on a copy so tests can write notes without touching real ones.
        # sqlite's own backup, not a file copy: it takes the WAL along with it.
        cls.tmp = tempfile.mkdtemp()
        cls.db = Path(cls.tmp) / "test.db"
        source = sqlite3.connect(SOURCE_DB)
        target = sqlite3.connect(cls.db)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()

        con = sqlite3.connect(cls.db)
        try:
            con.execute("DELETE FROM notes")  # start from an empty notebook
            con.commit()
        finally:
            con.close()
        os.environ["CONCORDANCE_DB"] = str(cls.db)

        from fastapi.testclient import TestClient

        from server import db, main

        db.DB_PATH = cls.db
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("CONCORDANCE_DB", None)

    # ---------------------------------------------------------------- data

    def test_all_four_translations_are_complete(self):
        meta = self.client.get("/api/meta").json()
        counts = meta["verse_counts"]
        self.assertEqual(set(counts), {"KJV", "ASV", "WEB", "BSB"})
        for code, n in counts.items():
            self.assertGreater(n, 30_000, code)
        self.assertEqual(len(meta["books"]), 66)

    def test_known_verses_are_right(self):
        text = self.client.get("/api/verse/JHN.3.16?translation=KJV").json()["verses"][0]
        self.assertIn("only begotten Son", text["text"])
        self.assertEqual(text["ref"], "JHN.3.16")

    def test_web_import_dropped_footnotes(self):
        # The USFX source wraps footnotes in <f>; they must not reach the text.
        gen = self.client.get("/api/verse/GEN.1.1?translation=WEB").json()["verses"][0]
        self.assertEqual(
            gen["text"], "In the beginning, God created the heavens and the earth."
        )

    # -------------------------------------------------------------- search

    def test_search_filters_by_translation(self):
        body = self.client.get("/api/search?q=anxious&translation=BSB").json()
        self.assertGreater(body["verse_total"], 0)
        self.assertTrue(all(v["translation"] == "BSB" for v in body["verses"]))

    def test_search_marks_the_matched_terms(self):
        body = self.client.get("/api/search?q=shepherd&translation=KJV").json()
        first = body["verses"][0]
        hits = [s["text"].lower() for s in first["segments"] if s["hit"]]
        self.assertTrue(hits)
        self.assertTrue(all("shepherd" in h for h in hits))
        # `text` stays clean -- markers are only in `segments`.
        self.assertNotIn(MARK_OPEN, first["text"])

    def test_canonical_sort_starts_at_genesis(self):
        body = self.client.get("/api/search?q=shepherd&sort=canonical").json()
        self.assertEqual(body["verses"][0]["book"], "GEN")

    def test_typing_a_topic_name_matches_topics(self):
        topics = self.client.get("/api/search?q=pray").json()["topics"]
        names = [t["name"] for t in topics]
        self.assertIn("PRAYER", names)
        self.assertGreater(topics[0]["ref_count"], 0)

    def test_hostile_query_does_not_500(self):
        for q in ['"', "-", "*", "AND", "NEAR(a b)", "a:b", "'; DROP TABLE verses--"]:
            with self.subTest(q=q):
                self.assertEqual(self.client.get("/api/search", params={"q": q}).status_code, 200)
        # and the table is still there
        self.assertTrue(self.client.get("/api/health").json()["ok"])
        self.assertGreater(self.client.get("/api/stats").json()["verses"], 0)

    def test_unknown_translation_is_rejected(self):
        self.assertEqual(self.client.get("/api/search?q=a&translation=NIV").status_code, 400)

    # -------------------------------------------------------------- topics

    def test_topic_detail_groups_by_heading(self):
        topic_id = self.client.get("/api/topics?q=prayer").json()["topics"][0]["id"]
        topic = self.client.get(f"/api/topics/{topic_id}?translation=WEB").json()
        self.assertGreater(topic["ref_count"], 100)
        first = topic["groups"][0]["refs"][0]
        self.assertRegex(first["ref"], r"^[1-3]?[A-Z]{2,3}\.\d+")
        self.assertTrue(first["text"])

    # ------------------------------------------------------------ reading

    def test_chapter_has_context_and_neighbours(self):
        ch = self.client.get("/api/chapter/PHP/4?translation=BSB").json()
        self.assertEqual(ch["label"], "Philippians 4")
        self.assertEqual(len(ch["verses"]), 23)
        self.assertEqual(ch["prev"], {"book": "PHP", "chapter": 3})
        self.assertEqual(ch["next"], {"book": "COL", "chapter": 1})

    def test_canon_ends_are_open(self):
        self.assertIsNone(self.client.get("/api/chapter/GEN/1").json()["prev"])
        self.assertIsNone(self.client.get("/api/chapter/REV/22").json()["next"])

    def test_missing_chapter_is_404(self):
        self.assertEqual(self.client.get("/api/chapter/PHP/99").status_code, 404)

    def test_cross_refs_come_from_naves_topics(self):
        body = self.client.get("/api/cross-refs/PHP.4.6").json()
        self.assertTrue(body["topics"])
        for group in body["topics"]:
            self.assertTrue(group["refs"])
            for ref in group["refs"]:
                # nothing covering the verse itself, including the whole-chapter
                # form PHP.4, which is not a cross-reference but a self-reference
                parsed = refs.parse(ref["ref"])
                self.assertIsNotNone(parsed, ref["ref"])
                covers = (
                    parsed.book == "PHP"
                    and parsed.chapter == 4
                    and (
                        parsed.verse_start == 0
                        or parsed.verse_start <= 6 <= parsed.verse_end
                    )
                )
                self.assertFalse(covers, f"{ref['ref']} covers PHP.4.6")

    # -------------------------------------------------- original languages

    def test_greek_interlinear(self):
        body = self.client.get("/api/interlinear/JHN.1.1").json()
        self.assertEqual(body["lang"], "grc")
        self.assertEqual(body["direction"], "ltr")
        self.assertGreaterEqual(len(body["words"]), 8)
        self.assertEqual([w["seq"] for w in body["words"]][:3], [1, 2, 3])
        logos = [w for w in body["words"] if w["strongs_base"] == "G3056"]
        self.assertTrue(logos)
        self.assertEqual(logos[0]["lemma"], "λόγος")
        self.assertIn("Noun", logos[0]["parsing"])
        # The English is carried alongside, never spliced into the words.
        self.assertIn("In the beginning", body["verse"]["text"])

    def test_hebrew_interlinear_reads_right_to_left(self):
        body = self.client.get("/api/interlinear/GEN.1.1").json()
        self.assertEqual(body["lang"], "heb")
        self.assertEqual(body["direction"], "rtl")
        self.assertEqual(body["words"][0]["strongs_base"], "H7225")
        self.assertEqual(body["words"][2]["lemma"], "אֱלֹהִים")

    def test_aramaic_is_marked_as_aramaic(self):
        # Daniel 2:4b-7:28 is Aramaic, and saying so is half the point.
        body = self.client.get("/api/interlinear/DAN.7.9").json()
        self.assertEqual(body["lang"], "arc")
        self.assertEqual(body["language"], "Aramaic")

    def test_psalm_superscription_leads_verse_one(self):
        # The title is verse 1 in Hebrew and unnumbered in English, so it is
        # filed as verse 0 and belongs at the head of verse 1.
        body = self.client.get("/api/interlinear/PSA.51.1").json()
        self.assertIn("choirmaster", " ".join(w["gloss"] for w in body["words"]))
        self.assertEqual([w["seq"] for w in body["words"]][:2], [1, 2])

    def test_affixes_have_no_dictionary_entry(self):
        # Prefixes are tagged H9xxx, which is STEPBible's extension: real
        # words to show, but Strong's never numbered them.
        # "in it" in Genesis 1:11 is a preposition with a pronoun suffix.
        words = self.client.get("/api/interlinear/GEN.1.11").json()["words"]
        affixes = [w for w in words if w["strongs_base"].startswith("H9")]
        self.assertTrue(affixes)
        self.assertFalse(any(w["in_dictionary"] for w in affixes))
        # They are still shown, with the sense the taggers gave them.
        self.assertTrue(all(w["gloss"] for w in affixes))

    def test_interlinear_rejects_junk_and_missing_verses(self):
        self.assertEqual(self.client.get("/api/interlinear/PHP.4").status_code, 400)
        self.assertEqual(self.client.get("/api/interlinear/PHP.99.1").status_code, 404)

    def test_strongs_entry(self):
        body = self.client.get("/api/strongs/G26").json()
        self.assertEqual(body["id"], "G26")
        self.assertEqual(body["lemma"], "ἀγάπη")
        self.assertGreater(body["occurrences"], 50)
        # Senses are folded, so "love", "love," and "Love" count as one.
        senses = [s["gloss"] for s in body["senses"]]
        self.assertEqual(len(senses), len(set(senses)))
        self.assertIn("love", senses)

    def test_strongs_lookup_forgives_the_input(self):
        for typed in ("h2617", "H02617", "H2617"):
            self.assertEqual(
                self.client.get(f"/api/strongs/{typed}").json()["id"], "H2617", typed
            )
        self.assertEqual(self.client.get("/api/strongs/grace").status_code, 400)
        self.assertEqual(self.client.get("/api/strongs/H9999").status_code, 404)

    def test_strongs_concordance_runs_in_canonical_order(self):
        body = self.client.get("/api/strongs/H2617/verses?limit=8").json()
        self.assertGreater(body["total"], 100)
        self.assertEqual(len(body["refs"]), 8)
        ordinals = []
        con = sqlite3.connect(self.db)
        try:
            for ref in body["refs"]:
                parsed = refs.parse(ref["ref"])
                self.assertIsNotNone(parsed, ref["ref"])
                ordinal = con.execute(
                    "SELECT ordinal FROM books WHERE code = ?", (parsed.book,)
                ).fetchone()[0]
                ordinals.append((ordinal, parsed.chapter, parsed.verse_start))
        finally:
            con.close()
        self.assertEqual(ordinals, sorted(ordinals))

    def test_strongs_concordance_pages_without_repeating(self):
        first = self.client.get("/api/strongs/G26/verses?limit=5").json()
        second = self.client.get("/api/strongs/G26/verses?limit=5&offset=5").json()
        self.assertEqual(first["total"], second["total"])
        self.assertFalse(
            {r["ref"] for r in first["refs"]} & {r["ref"] for r in second["refs"]}
        )

    def test_a_strongs_number_searched_returns_its_entry(self):
        body = self.client.get("/api/search?q=H2617").json()
        self.assertEqual(body["strongs"]["id"], "H2617")
        # And an ordinary search is unaffected.
        self.assertIsNone(self.client.get("/api/search?q=grace").json()["strongs"])

    # -------------------------------------------------------------- notes

    def test_note_lifecycle_and_search(self):
        created = self.client.post(
            "/api/notes",
            json={"verse_ref": "PHP.4.6", "body": "quernstone marginalia", "translation": "BSB"},
        )
        self.assertEqual(created.status_code, 201)
        note = created.json()
        self.assertEqual(note["label"], "Philippians 4:6")
        self.assertIn("anxious", note["verse_text"])

        found = self.client.get("/api/search?q=quernstone").json()["notes"]
        self.assertEqual([n["id"] for n in found], [note["id"]])

        self.client.patch(f"/api/notes/{note['id']}", json={"body": "rewritten entirely"})
        self.assertEqual(self.client.get("/api/search?q=quernstone").json()["notes"], [])
        self.assertEqual(len(self.client.get("/api/search?q=rewritten").json()["notes"]), 1)

        # the chapter view flags verses that carry notes
        ch = self.client.get("/api/chapter/PHP/4?translation=BSB").json()
        self.assertEqual([v["note_count"] for v in ch["verses"] if v["verse"] == 6], [1])

        self.assertEqual(self.client.delete(f"/api/notes/{note['id']}").status_code, 204)
        self.assertEqual(self.client.get("/api/notes").json()["notes"], [])
        self.assertEqual(self.client.delete(f"/api/notes/{note['id']}").status_code, 404)

    def test_note_with_an_unknown_translation_is_refused(self):
        for translation in ("NIV", "ALL"):
            r = self.client.post(
                "/api/notes",
                json={"verse_ref": "PHP.4.6", "body": "x", "translation": translation},
            )
            self.assertEqual(r.status_code, 400, translation)

    def test_oversized_reference_is_a_bad_request(self):
        r = self.client.get("/api/verse/PHP.99999999999999999999.1")
        self.assertEqual(r.status_code, 400)

    def require_spa(self):
        """The catch-all only exists when web/dist does, and it is registered at
        import time -- without it these two assert nothing."""
        from server import main

        if not any(getattr(r, "name", "") == "spa" for r in main.app.routes):
            self.skipTest("SPA fallback not mounted; run `make web` first")

    def test_unknown_api_path_is_404_not_the_spa(self):
        self.require_spa()
        r = self.client.get("/api/nonsense")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("<!doctype html>", r.text.lower())

    def test_spa_route_cannot_walk_out_of_the_build(self):
        self.require_spa()
        r = self.client.get("/../../etc/passwd")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("root:", r.text)

    def test_note_on_a_nonexistent_verse_is_refused(self):
        r = self.client.post("/api/notes", json={"verse_ref": "PHP.99.1", "body": "x"})
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/notes", json={"verse_ref": "PHP.4.6", "body": "   "})
        self.assertEqual(r.status_code, 400)

    def test_notes_survive_a_database_reopen(self):
        self.client.post("/api/notes", json={"verse_ref": "PSA.23.1", "body": "kept"})
        con = sqlite3.connect(self.db)
        try:
            rows = con.execute(
                "SELECT body FROM notes WHERE verse_ref = 'PSA.23.1'"
            ).fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [("kept",)])


if __name__ == "__main__":
    unittest.main()
