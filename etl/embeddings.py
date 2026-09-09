"""On-device "meaning" search: verse embeddings built with LSA.

Not a neural model -- there is no network at build time or run time, so this
is TF-IDF reduced with truncated SVD (classic latent semantic analysis). It
still recovers real semantic neighbours FTS5 can't: "light of the world"
reaches Isaiah 49:6 without the two verses sharing an unusual word, because
LSA groups words that keep turning up in the same verses.

Two things get written, both read-only at runtime like `verses`:

  verse_embeddings  one row per verse, the KJV text projected into the
                    reduced space.
  search_model      the one row a live query needs to land in the same
                    space: the vocabulary, its idf weights, and the SVD
                    projection matrix. `server/embeddings.py` re-implements
                    the TF-IDF transform by hand from these so the server
                    itself only needs numpy, not scikit-learn.

scikit-learn is a build-time-only dependency (etl/requirements.txt) -- it
never has to be installed where the app actually runs.
"""
from __future__ import annotations

import json
import sqlite3

import numpy as np

DIMS = 160
MAX_FEATURES = 12000
TOKEN_PATTERN = r"(?u)\b[a-zA-Z]{2,}\b"


def build(con: sqlite3.Connection) -> None:
    try:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError as exc:
        raise SystemExit(
            "meaning search needs scikit-learn at build time: "
            "pip install -r etl/requirements.txt"
        ) from exc

    rows = con.execute(
        "SELECT book, chapter, verse, text FROM verses"
        " WHERE translation = 'KJV' ORDER BY id"
    ).fetchall()
    locations = [(book, chapter, verse) for book, chapter, verse, _ in rows]
    texts = [text for *_, text in rows]

    vectorizer = TfidfVectorizer(
        token_pattern=TOKEN_PATTERN,
        stop_words="english",
        max_features=MAX_FEATURES,
        sublinear_tf=True,
        smooth_idf=True,
        norm="l2",
    )
    tfidf = vectorizer.fit_transform(texts)

    svd = TruncatedSVD(n_components=DIMS, random_state=0)
    embeddings = svd.fit_transform(tfidf).astype(np.float32)

    con.execute("DELETE FROM verse_embeddings")
    con.execute("DELETE FROM search_model")
    con.executemany(
        "INSERT INTO verse_embeddings(book, chapter, verse, vector) VALUES (?,?,?,?)",
        (
            (book, chapter, verse, vec.tobytes())
            for (book, chapter, verse), vec in zip(locations, embeddings)
        ),
    )

    vocabulary = {term: int(i) for term, i in vectorizer.vocabulary_.items()}
    idf = vectorizer.idf_.astype(np.float32)
    components = svd.components_.astype(np.float32)  # (DIMS, vocab_size)

    con.execute(
        "INSERT INTO search_model(id, dims, vocabulary, idf, components)"
        " VALUES (1, ?, ?, ?, ?)",
        (DIMS, json.dumps(vocabulary), idf.tobytes(), components.tobytes()),
    )

    print(
        f"  {len(rows):,} verses embedded, {len(vocabulary):,} terms, "
        f"{DIMS} dimensions ({svd.explained_variance_ratio_.sum():.0%} variance kept)"
    )
