-- Concordance schema.
--
-- Reference format used everywhere in the app is the "call number": BOK.C.V
-- (PHP.4.6). `book` columns hold the 3-letter USFM code, so a ref is always
-- reconstructible as book || '.' || chapter || '.' || verse.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    code      TEXT PRIMARY KEY,          -- GEN, PHP, ...
    name      TEXT NOT NULL,             -- Genesis, Philippians
    ordinal   INTEGER NOT NULL,          -- 1..66, canonical order
    testament TEXT NOT NULL              -- OT | NT
);

CREATE TABLE IF NOT EXISTS translations (
    code      TEXT PRIMARY KEY,          -- KJV, ASV, WEB, BSB
    name      TEXT NOT NULL,
    year      TEXT,
    license   TEXT NOT NULL,
    source    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verses (
    id          INTEGER PRIMARY KEY,
    book        TEXT NOT NULL REFERENCES books(code),
    chapter     INTEGER NOT NULL,
    verse       INTEGER NOT NULL,
    translation TEXT NOT NULL REFERENCES translations(code),
    text        TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS verses_unique
    ON verses(translation, book, chapter, verse);
CREATE INDEX IF NOT EXISTS verses_location
    ON verses(book, chapter, verse);

-- Full-text index over verse text. External-content table: the row data lives
-- in `verses`, FTS only stores the index. Rebuilt wholesale by the ETL, so no
-- sync triggers are needed here (verses are read-only at runtime).
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    content='verses',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS topics (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,        -- AARON, PRAYER, ...
    section TEXT                         -- the A-Z section it was filed under
);

CREATE TABLE IF NOT EXISTS topic_verses (
    id          INTEGER PRIMARY KEY,
    topic_id    INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    verse_ref   TEXT NOT NULL,           -- EXO.6.16-20 (range kept for display)
    book        TEXT NOT NULL REFERENCES books(code),
    chapter     INTEGER NOT NULL,
    verse_start INTEGER NOT NULL,        -- 0 == whole-chapter reference
    verse_end   INTEGER NOT NULL,
    heading     TEXT,                    -- Nave's sub-entry, e.g. "Lineage of"
    seq         INTEGER NOT NULL         -- original order within the topic
);

CREATE INDEX IF NOT EXISTS topic_verses_topic ON topic_verses(topic_id, seq);
CREATE INDEX IF NOT EXISTS topic_verses_loc
    ON topic_verses(book, chapter, verse_start);

-- Deliberately NOT stemmed. Topic names are looked up by prefix while typing,
-- and the porter stemmer rewrites a query prefix too: "pray" stems to "prai",
-- which prefix-matches PRAISE and misses PRAYER. Raw tokens + prefix behave the
-- way someone typing a topic name expects.
CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
    name,
    content='topics',
    content_rowid='id',
    tokenize='unicode61'
);

-- Personal notes. Unlike verses these change at runtime, so the FTS index is
-- kept in step with triggers.
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    verse_ref   TEXT NOT NULL,           -- PHP.4.6
    book        TEXT NOT NULL REFERENCES books(code),
    chapter     INTEGER NOT NULL,
    verse       INTEGER NOT NULL,
    translation TEXT,                    -- which translation was on screen
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS notes_ref ON notes(verse_ref);
CREATE INDEX IF NOT EXISTS notes_recent ON notes(updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    body,
    content='notes',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, body) VALUES ('delete', old.id, old.body);
    INSERT INTO notes_fts(rowid, body) VALUES (new.id, new.body);
END;
