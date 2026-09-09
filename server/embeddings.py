"""Query-time half of meaning search.

etl/embeddings.py fits a TF-IDF/SVD (LSA) model once, offline, and writes
every verse's projection into `verse_embeddings`. Turning a typed query into
the same space takes nothing scikit-learn wasn't already storing for us: a
vocabulary, an idf weight per term, and the SVD projection matrix, all in
`search_model`. This re-implements that one transform by hand in numpy so
the server doesn't carry scikit-learn as a dependency -- only the ETL does.

Loaded once, lazily, and kept in memory: 31k verses at a few hundred floats
each is a few tens of MB, and re-reading it from SQLite on every search would
be silly.
"""
from __future__ import annotations

import json
import re
import sqlite3

import numpy as np

_TOKEN = re.compile(r"[a-zA-Z]{2,}")


class MeaningIndex:
    def __init__(
        self,
        dims: int,
        vocabulary: dict[str, int],
        idf: np.ndarray,
        components: np.ndarray,
        locations: list[tuple[str, int, int]],
        matrix: np.ndarray,
    ):
        self.dims = dims
        self.vocabulary = vocabulary
        self.idf = idf
        self.components = components  # (dims, vocab_size)
        self.locations = locations  # [(book, chapter, verse), ...] row-aligned with matrix
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        self.matrix = matrix / np.where(norms == 0, 1, norms)  # unit rows -> dot == cosine

    def embed(self, text: str) -> np.ndarray | None:
        """Project a query into the same space verses were embedded into.

        Same recipe the ETL fit: sublinear term frequency times idf, L2
        normalised, then multiplied through the SVD projection. A query with
        no word in the vocabulary (all stopwords, or nothing recognised)
        has nothing to search with.
        """
        counts: dict[int, int] = {}
        for tok in _TOKEN.findall(text.lower()):
            idx = self.vocabulary.get(tok)
            if idx is not None:
                counts[idx] = counts.get(idx, 0) + 1
        if not counts:
            return None
        idxs = np.fromiter(counts.keys(), dtype=np.int64)
        tf = np.array([1.0 + np.log(c) for c in counts.values()], dtype=np.float32)
        tfidf = tf * self.idf[idxs]
        norm = np.linalg.norm(tfidf)
        if norm > 0:
            tfidf = tfidf / norm
        vec = self.components[:, idxs] @ tfidf
        vnorm = np.linalg.norm(vec)
        return vec / vnorm if vnorm > 0 else None

    def nearest(
        self, text: str, limit: int = 40
    ) -> list[tuple[tuple[str, int, int], float]]:
        """The closest verses by cosine similarity, best first."""
        vec = self.embed(text)
        if vec is None or not len(self.locations):
            return []
        sims = self.matrix @ vec
        n = min(limit, len(sims))
        top = np.argpartition(-sims, n - 1)[:n]
        top = top[np.argsort(-sims[top])]
        return [(self.locations[i], float(sims[i])) for i in top]


def load(con: sqlite3.Connection) -> MeaningIndex | None:
    """Read the model and every verse's vector out of the database.

    None if the database predates meaning search (no `search_model` row) --
    callers fall back to text-only search rather than failing outright.
    """
    try:
        row = con.execute(
            "SELECT dims, vocabulary, idf, components FROM search_model WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None

    dims = row["dims"]
    vocabulary = json.loads(row["vocabulary"])
    idf = np.frombuffer(row["idf"], dtype=np.float32)
    components = np.frombuffer(row["components"], dtype=np.float32).reshape(
        dims, len(vocabulary)
    )

    locations: list[tuple[str, int, int]] = []
    vectors: list[np.ndarray] = []
    for book, chapter, verse, blob in con.execute(
        "SELECT book, chapter, verse, vector FROM verse_embeddings"
    ):
        locations.append((book, chapter, verse))
        vectors.append(np.frombuffer(blob, dtype=np.float32))

    matrix = np.stack(vectors) if vectors else np.zeros((0, dims), dtype=np.float32)
    return MeaningIndex(dims, vocabulary, idf, components, locations, matrix)
