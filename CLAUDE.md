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
make setup    # venv, download sources (~130 MB), build the database, build the UI
make serve    # one process on 127.0.0.1:8000 (HOST=0.0.0.0 for the tailnet)
make dev      # API on 8000, Vite with hot reload on 5173
make test     # 58 tests, run before every commit
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
A new mutable table needs its own triggers. `original_words` and `strongs_entries`
are read-only too, and have no FTS index at all: a Strong's number is an exact key.

**The original languages are shown beside the English, never mapped onto it.** No
public dataset aligns these four translations to the Hebrew and Greek word for word,
so the interlinear sets the whole verse next to its original. Don't add a feature
that points at one English word and claims a particular Greek one without a real
alignment behind it.

**Strong's numbers get written four ways and stored one.** The tagged text says
`{H0430G}`, the dictionaries say `H430`, and people type `h2617` or `H02617`.
`etl/originals.py:normalise_strongs` and `server/originals.py:parse_strongs` are the
two doors in; everything past them is `H430`, unpadded, no suffix.

**A Hebrew word is several morphemes and only one of them is the word.** `H9005/{H4428G}`
is "to the" plus "king", and the braces mark the one carrying the dictionary entry.
The H9xxx numbers are STEPBible's extension for affixes and are not in Strong's, so
they show in the interlinear but open nothing.

**Verse 0 is a Psalm superscription**, not a bug. Hebrew counts the title as verse 1
and English Bibles print it unnumbered, so it is filed as verse 0 and served at the
head of verse 1.

**Original text is stored NFC.** The Greek arrives using the oxia accents, which are
canonically equivalent to the tonos ones and compare unequal — identical on screen,
different in a string test. Anything new that stores Hebrew or Greek normalises too.

**Search returns `segments`, not HTML.** The API marks hits with private-use
codepoints and splits them into `[{text, hit}]`. Never interpolate markup into
verse text.

## Design system

Tokens live at the top of `web/src/styles.css`: ink indigo `#1C2333`, parchment
`#E8DCC4`, oxblood `#7A2E2E`, verdigris `#5C7A6B`, paper `#F2ECD9`. Fraunces for
headings, Source Serif 4 for scripture, IBM Plex Mono for references and chrome.
Use the variables, don't hardcode hex.

Every reference renders through the `CallNumber` component: dark badge, light
monospace, identical everywhere. It's the signature element, so keep it consistent —
Strong's numbers wear the same stamp. Oxblood marks the primary track (scripture and
the original languages), verdigris the secondary (topics, notes, cross-references).
Fonts are bundled through fontsource; nothing loads from a CDN. Source Serif 4 covers
Greek; pointed Hebrew needs Noto Serif Hebrew, which is why it is imported separately.

The interlinear grid takes its `dir` from the language, which sets the reading order
of the word slips. Each slip is `dir="ltr"` inside, because its transliteration and
gloss are English and bidi otherwise drags their punctuation across: "and &lt;obj.&gt;"
comes out "&lt;.and &lt;obj".

## Before you call it done

Run `make test`. If the UI changed, build it (`cd web && npm run build`) and look at
it in a browser at 414px wide, not just at desktop width.
