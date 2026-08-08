# Concordance

A self-hosted personal Bible study app. Four public-domain translations, Nave's
Topical Bible as a topic index, full-text search over both, and your own notes —
all in one SQLite file, with no network calls at runtime.

Single user, no auth. Meant to sit on a homelab box and be reached over Tailscale.

```
make setup     # venv, download sources, build the database, build the UI
make serve     # http://localhost:8000  (API + UI from one process)
```

`make setup` takes a few minutes, almost all of it downloading ~26 MB of source
texts. It produces `data/concordance.db` (~40 MB), which is the whole app state —
back that file up and you have backed up your notes.

## Stack

| Layer    | Choice                                                          |
| -------- | --------------------------------------------------------------- |
| Backend  | FastAPI + Python's stdlib `sqlite3` (FTS5 is compiled in)         |
| Database | One SQLite file, WAL mode                                        |
| Frontend | React 18 + Vite, no UI framework, fonts self-hosted via fontsource |

Nothing is fetched from the internet while the app runs. The translations and
Nave's are pulled once by `etl/fetch_sources.py`; after that the app is fully
offline, which is the point of putting it behind Tailscale.

## Layout

```
etl/            one-time data pipeline
  fetch_sources.py   download the public-domain sources
  build_db.py        parse them into data/concordance.db
  schema.sql         the schema, commented
  books.py           canonical 66-book table + name/code resolution
server/         FastAPI app (main.py, search.py, refs.py, db.py)
web/            React SPA (src/views.jsx, components.jsx, sheets.jsx, styles.css)
tests/          unittest suite: parsing rules + full API coverage
```

## Data

| Source                                        | Used for      | License                    |
| --------------------------------------------- | ------------- | -------------------------- |
| [scrollmapper/bible_databases][sm]             | KJV, ASV, BSB | Public domain texts        |
| [seven1m/open-bibles][ob] (`eng-web.usfx.xml`) | WEB           | Public domain              |
| [BradyStephenson/bible-data][bd]               | Nave's        | Dataset CC BY 4.0; Nave's itself is public domain |

[sm]: https://github.com/scrollmapper/bible_databases
[ob]: https://github.com/seven1m/open-bibles
[bd]: https://github.com/BradyStephenson/bible-data

Two notes on sourcing:

- **WEB comes from a different source than the other three.** scrollmapper has no
  WEB, so it is parsed out of USFX XML instead, dropping footnote and
  cross-reference apparatus so only scripture text is indexed.
- **bolls.life was unreachable** from the machine this was built on (the outbound
  proxy refuses it), so the translations come from GitHub-hosted datasets. Same
  public-domain texts, different host.

Loaded: 124,372 verses across four translations, 4,667 topics, 76,141 topical
references. The ETL discards references that do not resolve to a real verse
(62 of them, mis-read out of Nave's prose headings).

## Schema

```sql
verses(id, book, chapter, verse, translation, text)          -- book is a USFM code: GEN, PHP
topics(id, name, section)
topic_verses(topic_id, verse_ref, book, chapter, verse_start, verse_end, heading, seq)
notes(id, verse_ref, book, chapter, verse, translation, body, created_at, updated_at)
books(code, name, ordinal, testament)
translations(code, name, year, license, source)
```

`verse_ref` is the call number: `PHP.4.6`, or `PHP.4.6-7` for a range, or `NUM.17`
for a whole chapter. The normalised `book`/`chapter`/`verse_*` columns sit
alongside it so references can be joined against verses without parsing strings.

Three FTS5 indexes: `verses_fts` and `notes_fts` (porter-stemmed, so "loved"
finds "love"), and `topics_fts` (deliberately **not** stemmed — porter rewrites a
query prefix, so "pray" would prefix-match PRAISE and miss PRAYER).

`verses` is read-only at runtime and its index is built wholesale by the ETL.
`notes` change constantly, so triggers keep `notes_fts` in step.

## API

| Endpoint                             | Does                                                       |
| ------------------------------------ | ---------------------------------------------------------- |
| `GET /api/meta`                      | translations, books, chapter counts                        |
| `GET /api/search?q=&translation=&sort=` | verses + matching topic names + your notes, one call     |
| `GET /api/topics?q=`                 | topic names with reference counts                          |
| `GET /api/topics/{id}`               | one topic, references grouped under Nave's sub-headings     |
| `GET /api/chapter/{book}/{chapter}`  | full chapter, prev/next, per-verse note counts              |
| `GET /api/verse/{ref}`               | one verse, one or all translations                          |
| `GET /api/cross-refs/{ref}`          | related verses via shared Nave's topics                     |
| `GET/POST/PATCH/DELETE /api/notes`   | personal notes                                              |

Interactive docs at `/api/docs`.

Search results carry both `text` (clean) and `segments` (`[{text, hit}]`) so the
UI can mark matched terms without interpolating HTML. `sort=relevance` (bm25) is
the default; `sort=canonical` walks Genesis to Revelation. Whatever is typed is
treated as literal words — quotes, `-`, `*` and `AND` are quoted into inert
terms rather than reaching FTS5 as operators, and `"phrases in quotes"` are kept
whole.

**Cross-references are derived, not sourced.** There is no cross-reference
dataset in v1: two verses are related when Nave's files them under the same
topic, smallest topics first.

## Design

Colours: ink indigo `#1C2333` ground, parchment `#E8DCC4` type, oxblood `#7A2E2E`
primary, verdigris `#5C7A6B` secondary, paper `#F2ECD9` cards. Fraunces for
headers, Source Serif 4 for body and scripture, IBM Plex Mono for references,
labels and all UI chrome.

Every reference renders as a call-number stamp — dark badge, light monospace type
— on cards, in sheets, in the reader header, in the pager. Result cards are paper
with an oxblood left spine; verdigris marks the secondary track (topics, notes,
cross-refs). Mobile-first, bottom tab bar: Search / Topics / Read / Notes.

Fonts are bundled into `web/dist`, so nothing loads from Google's CDN.

> Heads up: the static HTML mockup mentioned in the brief never arrived in this
> session — no attachment came through. The visual system above is built from the
> written spec (colours, type, stamps, cards, tab bar). If you send the mockup,
> matching the remaining details is a small pass over `web/src/styles.css`.

## Running it on the homelab

`make serve` binds `0.0.0.0:8000` so it is reachable over Tailscale. It has no
auth by design — keep it on the tailnet, not on a public interface.

```ini
# /etc/systemd/system/concordance.service
[Unit]
Description=Concordance
After=network.target

[Service]
WorkingDirectory=/srv/concordance
ExecStart=/srv/concordance/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=you

[Install]
WantedBy=multi-user.target
```

For development, `make dev` runs the API on 8000 and Vite with hot reload on
5173, proxying `/api` across.

## Tests

```
make test     # 34 tests
```

Parsing rules (book codes, Nave's reference grammar, call numbers, FTS query
building) and the full API against a scratch copy of the real database.

## Not in v1

Commentaries, Strong's and original languages, cloud sync, multi-user, reading
plans. Song of Solomon has no entries in the Nave's dataset used here, so it
appears in search and reading but not under any topic.
