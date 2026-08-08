"""End-to-end checks against a real (small) database built by the ETL.

Skipped entirely when data/concordance.db has not been built yet.
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

SOURCE_DB = Path(os.environ.get("CONCORDANCE_DB", ROOT / "data" / "concordance.db"))


@unittest.skipUnless(SOURCE_DB.exists(), f"{SOURCE_DB} not built (run: make data)")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Work on a copy so tests can write notes without touching real ones.
        cls.tmp = tempfile.mkdtemp()
        cls.db = Path(cls.tmp) / "test.db"
        shutil.copy(SOURCE_DB, cls.db)
        with sqlite3.connect(cls.db) as con:
            con.execute("DELETE FROM notes")  # start from an empty notebook
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
        self.assertNotIn("", first["text"])

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
        self.assertGreater(self.client.get("/api/health").json()["verses"], 0)

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
            # the verse itself is never listed as its own cross-reference
            self.assertNotIn("PHP.4.6", [r["ref"] for r in group["refs"]])

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

    def test_note_on_a_nonexistent_verse_is_refused(self):
        r = self.client.post("/api/notes", json={"verse_ref": "PHP.99.1", "body": "x"})
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/notes", json={"verse_ref": "PHP.4.6", "body": "   "})
        self.assertEqual(r.status_code, 400)

    def test_notes_survive_a_database_reopen(self):
        self.client.post("/api/notes", json={"verse_ref": "PSA.23.1", "body": "kept"})
        with sqlite3.connect(self.db) as con:
            rows = con.execute("SELECT body FROM notes WHERE verse_ref = 'PSA.23.1'").fetchall()
        self.assertEqual(rows, [("kept",)])


if __name__ == "__main__":
    unittest.main()
