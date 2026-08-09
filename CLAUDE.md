# Working in this repo

Concordance is a single-user Bible study app: FastAPI over SQLite/FTS5, a React
SPA, and one database file that holds scripture, Nave's Topical Bible, and personal
notes. Read the README first, it explains the shape of the thing.

## Commits and attribution

Commits belong to the repo owner. Author every commit as:

```text
TheShield2594 <82059300+TheShield2594@users.noreply.github.com>
```

Set it before committing so it can't be forgotten:

```sh
git config user.name "TheShield2594"
git config user.email "82059300+TheShield2594@users.noreply.github.com"
```

Keep the `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer at the
bottom of the message. Owner authors, Claude co-authors, and GitHub attributes the
contribution to the account that owns the repo.

Work on `claude/concordance-bible-app-44mnid` unless told otherwise. Push with
`git push -u origin <branch>`. Don't open a pull request unless asked.

## Commands

```sh
make setup    # venv, download sources, build the database, build the UI
make serve    # one process on 127.0.0.1:8000 (HOST=0.0.0.0 for the tailnet)
make dev      # API on 8000, Vite with hot reload on 5173
make test     # 38 tests, run before every commit
make data     # rebuild data/concordance.db from the downloaded sources
make clean    # build artifacts only, leaves the database alone
make reset    # destructive: deletes the database, notes and all
```

`make test` needs `data/concordance.db` to exist, and fails rather than skips without
it, so a CI run can't come back green having asserted nothing. Set
`CONCORDANCE_ALLOW_SKIP=1` to skip instead. The API tests take a sqlite backup of the
database and clear its notes, so they never touch real notes.

**Rebuilding keeps your notes.** `etl/build_db.py` lifts them out before it replaces
the file and puts them back after. Anything that touches that path needs to keep
that true.

## Rules that aren't obvious from the code

**Nothing calls the network at runtime.** `etl/fetch_sources.py` downloads the
public domain texts once at setup. If a feature seems to need a live API, it
doesn't belong in this app.

**References are USFM call numbers.** `PHP.4.6`, `PHP.4.6-7` for a range, `NUM.17`
for a whole chapter. Three-letter book codes throughout: PHP not PHIL, MRK not MAR,
SNG not SOS. `etl/books.py` is the only place that maps names to codes; add source
spellings there rather than special-casing a parser.

**User input never reaches FTS5 raw.** `server/search.py` tokenises and quotes it,
so a stray `-` or the word `AND` searches for itself instead of raising a syntax
error. Anything new that touches MATCH goes through `build_match`.

**Topic names are indexed unstemmed on purpose.** Porter rewrites the query prefix
along with the index, so "pray" stems to "prai," prefix-matches PRAISE, and never
reaches PRAYER. Verse and note text keep the stemmer. Don't unify the tokenizers.

**`verses` is read-only after the ETL.** Its FTS index gets rebuilt wholesale, no
triggers. `notes` change at runtime and have triggers keeping `notes_fts` in step.
A new mutable table needs its own triggers.

**Search returns `segments`, not HTML.** The API marks hits with private-use
codepoints and splits them into `[{text, hit}]`. Never interpolate markup into
verse text.

## Design system

Tokens live at the top of `web/src/styles.css`: ink indigo `#1C2333`, parchment
`#E8DCC4`, oxblood `#7A2E2E`, verdigris `#5C7A6B`, paper `#F2ECD9`. Fraunces for
headings, Source Serif 4 for scripture, IBM Plex Mono for references and chrome.
Use the variables, don't hardcode hex.

Every reference renders through the `CallNumber` component: dark badge, light
monospace, identical everywhere. It's the signature element, so keep it consistent.
Oxblood marks the primary track, verdigris the secondary (topics, notes,
cross-references). Fonts are bundled through fontsource; nothing loads from a CDN.

## Before you call it done

Run `make test`. If the UI changed, build it (`cd web && npm run build`) and look at
it in a browser at 414px wide, not just at desktop width.
