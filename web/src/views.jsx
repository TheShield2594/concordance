import { useEffect, useMemo, useRef, useState } from 'react'

import { api } from './api.js'
import {
  Badge,
  Chips,
  Empty,
  ErrorNote,
  Marked,
  Panel,
  ReadingModeSwitch,
  Reference,
  ResultRow,
  SearchField,
  Section,
  Spinner,
  TopicRow,
} from './components.jsx'
import { formatDate } from './format.js'
import { useAsync, useDebounced, useStoredJSON } from './hooks.js'
import {
  IconBookmark,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconNote,
  IconOriginal,
  IconOrnament,
  IconPlay,
  IconShare,
} from './icons.jsx'

const PAGE = 25
const SEARCH_MODES = [
  { id: 'meaning', label: 'Meaning' },
  { id: 'exact', label: 'Exact' },
  { id: 'strongs', label: "Strong's" },
]

async function share(text) {
  if (navigator.share) {
    try {
      await navigator.share({ text })
      return
    } catch (e) {
      // Cancelling the share sheet is the one rejection that means "stop
      // here" -- anything else (no permission, an unshareable payload) is a
      // real failure the clipboard fallback below should still attempt.
      if (e.name === 'AbortError') return
    }
  }
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    /* clipboard unavailable -- silently give up rather than throw into the UI */
  }
}

/* ------------------------------------------------------------------- today */

export function TodayView({ actions, navigate, readable, threadsVersion }) {
  const { data, error, loading } = useAsync(
    () => api.today(readable),
    [readable, threadsVersion],
  )
  const [lastRead] = useStoredJSON('concordance.lastRead', null)
  const [lastTopic] = useStoredJSON('concordance.lastTopic', null)
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }).format(new Date())

  const verse = data?.verse_of_day?.verse
  const openVerse = () =>
    verse && navigate(`read/${verse.book}/${verse.chapter}?v=${verse.verse}`)

  return (
    <div className="view">
      <div className="view-head">
        <span className="eyebrow">{today}</span>
        <h1>Today</h1>
      </div>

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {verse && (
        <Panel variant="soft" className="today-hero">
          <span className="today-hero__ornament">
            <IconOrnament size={18} />
          </span>
          <span className="panel__eyebrow">Verse of the day</span>
          {/* The composition holds a short verse beautifully and a long one
              badly, so a long one keeps the composition and loses a size. */}
          <p
            className={`today-hero__text${
              verse.text.length > 120 ? ' today-hero__text--long' : ''
            }`}
          >
            {verse.text}
          </p>
          <Reference
            aside={verse.translation}
            onClick={openVerse}
            title="Open in the reader"
          >
            {data.verse_of_day.label}
          </Reference>
          <div className="today-hero__actions">
            <button
              type="button"
              className="today-hero__action"
              onClick={() => actions.note(verse.ref, verse.translation)}
            >
              <IconBookmark size={17} /> Note
            </button>
            <button
              type="button"
              className="today-hero__action"
              onClick={() => share(`${verse.text} — ${data.verse_of_day.label}`)}
            >
              <IconShare size={17} /> Share
            </button>
          </div>
        </Panel>
      )}

      <section className="section">
        <div className="section__head">
          <span className="section__title">Continue reading</span>
        </div>
        {lastRead ? (
          <Panel className="stack stack--tight">
            <div className="today-hero__foot">
              <div>
                <p className="panel__title" style={{ fontSize: '1.2rem' }}>
                  {lastRead.label}
                </p>
                <span className="tag">{lastRead.book_name}</span>
              </div>
              <button
                type="button"
                className="icon-btn"
                title="Resume reading"
                onClick={() => navigate(`read/${lastRead.book}/${lastRead.chapter}`)}
                style={{
                  width: '2.75rem',
                  height: '2.75rem',
                  borderRadius: '50%',
                  background: 'var(--primary)',
                  color: 'var(--primary-foreground)',
                }}
              >
                <IconPlay size={16} />
              </button>
            </div>
          </Panel>
        ) : (
          <Panel className="muted">Nothing read yet — try John 1 or Psalm 23.</Panel>
        )}
      </section>

      {(data?.recent_thread || lastTopic) && (
        <section className="section">
          <div className="section__head">
            <span className="section__title">Picking up where you left off</span>
          </div>
          <div className="today-row">
            {data?.recent_thread && (
              <Panel
                variant="dark"
                as="button"
                className="today-card"
                onClick={() => navigate(`notes/threads/${data.recent_thread.id}`)}
              >
                <span className="panel__eyebrow">Study thread</span>
                <p className="today-card__title">{data.recent_thread.name}</p>
                <span className="today-card__foot">
                  {data.recent_thread.item_count} {data.recent_thread.item_count === 1 ? 'verse' : 'verses'} ·{' '}
                  {data.recent_thread.note_count} {data.recent_thread.note_count === 1 ? 'note' : 'notes'}
                </span>
              </Panel>
            )}
            {lastTopic && (
              <Panel
                variant="soft"
                as="button"
                className="today-card"
                onClick={() => navigate(`topics/${lastTopic.id}`)}
              >
                <span className="panel__eyebrow">Topic</span>
                <p className="today-card__title">{lastTopic.name}</p>
                <span className="today-card__foot">Nave's</span>
              </Panel>
            )}
          </div>
        </section>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ search */

export function SearchView({ route, navigate, translation, setTranslation, chips, actions }) {
  const [q, setQ] = useState(route.query.q ?? '')
  const query = useDebounced(q, 200)
  const [mode, setMode] = useState('meaning')
  const [extra, setExtra] = useState([])
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState(null)
  const [sort, setSort] = useState('relevance')

  useEffect(() => {
    navigate(query ? `search?q=${encodeURIComponent(query)}` : 'search', { replace: true })
  }, [query, navigate])

  const { data, error, loading } = useAsync(
    () => api.search({ q: query, translation, limit: PAGE, sort, mode }),
    [query, translation, sort, mode],
    { skip: !query.trim() },
  )

  useEffect(() => setExtra([]), [query, translation, sort, mode])

  const verses = useMemo(() => [...(data?.verses ?? []), ...extra], [data, extra])
  // verse_total is the true FTS count and the paging cursor "Load more" has
  // to respect; meaning-only extras ride along on page 1 but aren't part of
  // that count, so they're excluded from the offset math too, or the next
  // fetch would skip past real FTS results the extras' count stood in for.
  const ftsLoaded = useMemo(
    () => verses.filter((v) => v.match_kind !== 'meaning').length,
    [verses],
  )
  const more = data ? ftsLoaded < data.verse_total : false

  const loadMore = async () => {
    setLoadingMore(true)
    setMoreError(null)
    try {
      const next = await api.search({
        q: query,
        translation,
        limit: PAGE,
        offset: ftsLoaded,
        include: 'verses',
        sort,
        mode,
      })
      setExtra((rows) => [...rows, ...next.verses])
    } catch (e) {
      setMoreError(e)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div className="view">
      <div className="view-head">
        <h1>Search</h1>
      </div>

      <SearchField
        value={q}
        onChange={setQ}
        placeholder="Search scripture, topics and notes"
        autoFocus
      />

      <div className="chips">
        {SEARCH_MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            className="chip"
            aria-pressed={mode === m.id}
            onClick={() => setMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <Chips options={chips} value={translation} onChange={setTranslation} label="Translation" />

      {!query.trim() && (
        <Empty mark="Concordance">
          <p>
            Search the text of four translations, the topics of Nave's, and your own
            notes — all at once.
          </p>
          <p>A reference — John 3:16, PHP.4.6 — or a Strong's number jumps straight to it.</p>
        </Empty>
      )}

      {loading && <Spinner />}
      <ErrorNote error={error} />

      {data?.reference && (
        <ReferenceCard reference={data.reference} navigate={navigate} actions={actions} />
      )}

      {mode === 'strongs' && data?.strongs_matches?.length > 0 && (
        <Section title="Original language" aside={`${data.strongs_matches.length} matching`}>
          <div className="results">
            {data.strongs_matches.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className="result"
                style={{ textAlign: 'left', background: 'none', border: 0, width: '100%' }}
                onClick={() => actions.strongs(entry.id)}
              >
                <div className="result__head">
                  <span className="result__ref">{entry.lemma}</span>
                  <Badge>{entry.id}</Badge>
                </div>
                <p className="result__text" style={{ fontSize: '1rem' }}>
                  {entry.translit} · {entry.occurrences.toLocaleString()}× — {entry.definition}
                </p>
              </button>
            ))}
          </div>
        </Section>
      )}

      {mode !== 'strongs' && data?.strongs && (
        <Section title="Original language" aside={data.strongs.language}>
          <button
            type="button"
            className="panel"
            style={{ textAlign: 'left', width: '100%', display: 'block', cursor: 'pointer' }}
            onClick={() => actions.strongs(data.strongs.id)}
          >
            <div className="result__head">
              <Badge>{data.strongs.id}</Badge>
              <span className="tag">{data.strongs.translit}</span>
              <span className="tag" style={{ marginLeft: 'auto' }}>
                {data.strongs.occurrences.toLocaleString()}×
              </span>
            </div>
            <p className={`lemma lemma--${data.strongs.lang}`} dir={data.strongs.direction}>
              {data.strongs.lemma}
            </p>
            <p className="result__text" style={{ fontSize: '1rem' }}>{data.strongs.definition}</p>
            <div className="result__actions">
              <span className="result__action">Every occurrence →</span>
            </div>
          </button>
        </Section>
      )}

      {data?.topics?.length > 0 && (
        <Section title="Topics" aside={`${data.topics.length} matching`}>
          <div className="stack">
            {data.topics.map((topic) => (
              <TopicRow key={topic.id} topic={topic} onOpen={(t) => navigate(`topics/${t.id}`)} />
            ))}
          </div>
        </Section>
      )}

      {data?.notes?.length > 0 && (
        <Section title="Your notes" aside={`${data.notes.length}`}>
          <div className="results">
            {data.notes.map((note) => (
              <article key={note.id} className="result">
                <div className="result__head">
                  <button
                    type="button"
                    className="result__ref"
                    style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                    onClick={() => actions.note(note.verse_ref)}
                  >
                    {note.verse_ref}
                  </button>
                  <span className="result__kind">Note</span>
                </div>
                <p className="note-body">
                  <Marked segments={note.segments} text={note.body} />
                </p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {mode !== 'strongs' &&
        data &&
        !(data.verse_total === 0 && (data.strongs || data.reference)) && (
          <Section
            title="Verses"
            aside={
              data.verse_total ? (
                <>
                  {data.verse_total.toLocaleString()} in{' '}
                  {translation === 'ALL' ? 'all translations' : translation} ·{' '}
                  <button
                    type="button"
                    className="link"
                    onClick={() => setSort(sort === 'relevance' ? 'canonical' : 'relevance')}
                    title="Switch between best-match and Genesis-to-Revelation order"
                  >
                    {sort === 'relevance' ? 'By relevance' : 'In order'}
                  </button>
                </>
              ) : undefined
            }
          >
            {data.verse_total === 0 && !loading && !data.strongs && !data.reference ? (
              <Empty mark="No verses">
                <p>Nothing matched “{query}”.</p>
              </Empty>
            ) : (
              <div className="results">
                {verses.map((verse) => (
                  <ResultRow
                    key={`${verse.translation}-${verse.id}`}
                    verse={verse}
                    onRead={(v) => navigate(`read/${v.book}/${v.chapter}?v=${v.verse}`)}
                    onNote={(v) => actions.note(v.ref, v.translation)}
                    onCrossRefs={(v) => actions.crossRefs(v.ref)}
                    onOriginal={(v) => actions.original(v.ref)}
                  />
                ))}
                <ErrorNote error={moreError} />
                {more && (
                  <button type="button" className="btn" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore ? 'Loading…' : 'Load more'}
                  </button>
                )}
              </div>
            )}
          </Section>
        )}
    </div>
  )
}

function ReferenceCard({ reference, navigate, actions }) {
  const single = reference.verse_start > 0
  const range = reference.verse_end > reference.verse_start
  const firstRef = `${reference.book}.${reference.chapter}.${reference.verse_start}`
  const read = () =>
    navigate(
      `read/${reference.book}/${reference.chapter}${single ? `?v=${reference.verse_start}` : ''}`,
    )

  return (
    <Section title="Reference" aside={reference.book_name}>
      <Panel>
        <div className="result__head">
          <button
            type="button"
            className="result__ref"
            style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
            onClick={read}
          >
            {reference.label}
          </button>
        </div>
        {reference.verses.length > 0 && (
          <div className="stack">
            {reference.verses.map((verse) => (
              <p key={`${verse.translation}-${verse.id}`} className="result__text">
                {verse.text}{' '}
                <span className="tag">
                  {range ? `v${verse.verse} · ` : ''}
                  {verse.translation}
                </span>
              </p>
            ))}
          </div>
        )}
        <div className="result__actions">
          <button type="button" className="result__action" onClick={read}>
            Read chapter
          </button>
          {single && (
            <>
              <button type="button" className="result__action" onClick={() => actions.note(firstRef)}>
                Add note
              </button>
              <button
                type="button"
                className="result__action"
                onClick={() => actions.crossRefs(firstRef)}
              >
                Cross-refs
              </button>
              <button
                type="button"
                className="result__action"
                onClick={() => actions.original(firstRef)}
              >
                Original
              </button>
            </>
          )}
        </div>
      </Panel>
    </Section>
  )
}

/* ------------------------------------------------------------------ topics */

export function TopicsView({ route, navigate, readable, actions }) {
  const topicId = route.parts[0]
  if (topicId) {
    return <TopicDetail topicId={topicId} navigate={navigate} readable={readable} actions={actions} />
  }
  return <TopicList navigate={navigate} />
}

function TopicList({ navigate }) {
  const [q, setQ] = useState('')
  const query = useDebounced(q, 200)
  const { data, error, loading } = useAsync(() => api.topics({ q: query }), [query])

  return (
    <div className="view">
      <div className="view-head">
        <h1>Topics</h1>
      </div>
      <SearchField value={q} onChange={setQ} placeholder="Search Nave's topics" />
      {loading && <Spinner label="Looking up" />}
      <ErrorNote error={error} />
      <Section
        title={query ? 'Matching topics' : "Nave's largest topics"}
        aside={data ? `${data.topics.length}` : undefined}
      >
        <div className="stack">
          {data?.topics?.map((topic) => (
            <TopicRow key={topic.id} topic={topic} onOpen={(t) => navigate(`topics/${t.id}`)} />
          ))}
        </div>
        {data?.topics?.length === 0 && (
          <Empty mark="No topics">
            <p>Nave's has nothing filed under “{query}”.</p>
          </Empty>
        )}
      </Section>
    </div>
  )
}

function TopicDetail({ topicId, navigate, readable, actions }) {
  const { data, error, loading } = useAsync(() => api.topic(topicId, readable), [topicId, readable])
  const [, setLastTopic] = useStoredJSON('concordance.lastTopic', null)

  useEffect(() => {
    if (data) setLastTopic({ id: data.id, name: data.name })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.id])

  const readTarget = (ref) =>
    `read/${ref.book}/${ref.chapter}${ref.verse_start > 0 ? `?v=${ref.verse_start}` : ''}`

  return (
    <div className="view">
      <div className="section__head">
        <button type="button" className="link" onClick={() => navigate('search')}>
          ← Search
        </button>
        <span className="tag">{data ? `${data.ref_count} refs · ${data.translation}` : ''}</span>
      </div>

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <>
          <h1 className="serif" style={{ fontWeight: 400, margin: 0, fontSize: '1.8rem' }}>
            {data.name}
          </h1>
          {data.groups.map((group, i) => (
            <Section key={i} title={group.heading || 'References'}>
              <div className="results">
                {group.refs.map((ref, j) => (
                  <article key={`${ref.ref}-${j}`} className="result">
                    <div className="result__head">
                      <button
                        type="button"
                        className="result__ref"
                        style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                        onClick={() => navigate(readTarget(ref))}
                      >
                        {ref.label}
                      </button>
                    </div>
                    {ref.text && <p className="result__text">{ref.text}</p>}
                    <div className="result__actions">
                      <button
                        type="button"
                        className="result__action"
                        onClick={() => navigate(readTarget(ref))}
                      >
                        Read chapter
                      </button>
                      {ref.verse_start > 0 && (
                        <button
                          type="button"
                          className="result__action"
                          onClick={() =>
                            actions.note(`${ref.book}.${ref.chapter}.${ref.verse_start}`, data.translation)
                          }
                        >
                          Add note
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </Section>
          ))}
        </>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------- read */

export function ReadView({
  route,
  navigate,
  readable,
  chooseReading,
  meta,
  actions,
  notesVersion,
  highlightsVersion,
  readingMode,
  setReadingMode,
  desktop,
  focusedRef,
  onFocusVerse,
}) {
  const [book, chapter] = route.parts
  const chips = (meta?.translation_chips ?? []).filter((t) => t !== 'ALL')

  if (!book) return <BookPicker meta={meta} navigate={navigate} />
  if (!chapter) return <ChapterPicker meta={meta} book={book} navigate={navigate} />

  return (
    <Chapter
      book={book}
      chapter={Number(chapter)}
      focus={Number(route.query.v) || 0}
      translation={readable}
      setTranslation={chooseReading}
      chips={chips}
      navigate={navigate}
      actions={actions}
      notesVersion={notesVersion}
      highlightsVersion={highlightsVersion}
      readingMode={readingMode}
      setReadingMode={setReadingMode}
      desktop={desktop}
      focusedRef={focusedRef}
      onFocusVerse={onFocusVerse}
    />
  )
}

function BookPicker({ meta, navigate }) {
  const books = meta?.books ?? []
  return (
    <div className="view">
      <div className="view-head">
        <h1>Read</h1>
      </div>
      {['OT', 'NT'].map((testament) => (
        <Section key={testament} title={testament === 'OT' ? 'Old Testament' : 'New Testament'}>
          <div className="grid grid--books">
            {books
              .filter((b) => b.testament === testament)
              .map((b) => (
                <button key={b.code} type="button" className="tile" onClick={() => navigate(`read/${b.code}`)}>
                  {b.code}
                  <span className="tile__name">{b.name}</span>
                </button>
              ))}
          </div>
        </Section>
      ))}
    </div>
  )
}

function ChapterPicker({ meta, book, navigate }) {
  const info = (meta?.books ?? []).find((b) => b.code === book.toUpperCase())
  const count = info?.chapters ?? 0
  return (
    <div className="view">
      <div className="section__head">
        <button type="button" className="link" onClick={() => navigate('read')}>
          ← Books
        </button>
      </div>
      <Section title={info ? info.name : book} aside={`${count} chapters`}>
        <div className="grid grid--chapters">
          {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
            <button key={n} type="button" className="tile" onClick={() => navigate(`read/${book.toUpperCase()}/${n}`)}>
              {n}
            </button>
          ))}
        </div>
      </Section>
    </div>
  )
}

/** Which verse (by `data-ref`) a non-collapsed selection currently sits in. */
function useVerseSelection(containerRef) {
  const [ref, setRef] = useState(null)
  useEffect(() => {
    const onChange = () => {
      const sel = window.getSelection()
      if (!sel || sel.isCollapsed || !containerRef.current) {
        setRef(null)
        return
      }
      const node = sel.anchorNode
      if (!node || !containerRef.current.contains(node)) {
        setRef(null)
        return
      }
      const el = (node.nodeType === 1 ? node : node.parentElement)?.closest('[data-ref]')
      setRef(el?.dataset.ref ?? null)
    }
    document.addEventListener('selectionchange', onChange)
    return () => document.removeEventListener('selectionchange', onChange)
  }, [containerRef])
  return [ref, () => window.getSelection()?.removeAllRanges()]
}

export function Chapter({
  book,
  chapter,
  focus,
  translation,
  setTranslation,
  chips,
  navigate,
  actions,
  notesVersion,
  highlightsVersion,
  readingMode,
  setReadingMode,
  desktop,
  focusedRef,
  onFocusVerse,
}) {
  const { data, error, loading } = useAsync(
    () => api.chapter(book, chapter, translation),
    [book, chapter, translation, notesVersion, highlightsVersion],
  )
  const containerRef = useRef(null)
  const [selectionRef, clearSelection] = useVerseSelection(containerRef)
  const selectedRef = desktop ? null : selectionRef
  const [, setLastRead] = useStoredJSON('concordance.lastRead', null)

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [book, chapter])

  useEffect(() => {
    if (!data) return
    document.getElementById(`verse-${focus}`)?.scrollIntoView({ block: 'center' })
  }, [data, focus])

  useEffect(() => {
    if (!data) return
    setLastRead({ book: data.book, book_name: data.book_name, chapter: data.chapter, label: data.label })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.book, data?.chapter])

  const selectedVerse = data?.verses.find((v) => v.ref === selectedRef)

  const withSelection = (fn) => () => {
    fn()
    clearSelection()
  }

  return (
    <div className={desktop ? 'desktop__reader-inner' : 'view'}>
      {!desktop && (
        <div className="reader__head">
          <button type="button" className="link" onClick={() => navigate(`read/${book.toUpperCase()}`)}>
            ← Chapters
          </button>
          <div className="reader__head-left">
            <Reference
              aside={<IconChevronDown size={12} />}
              onClick={() => navigate(`read/${book.toUpperCase()}`)}
              title="Pick a chapter"
            >
              {data?.label ?? `${book.toUpperCase()} ${chapter}`}
            </Reference>
            <ReadingModeSwitch value={readingMode} onChange={setReadingMode} />
          </div>
        </div>
      )}

      {!desktop && (
        <Chips options={chips} value={translation} onChange={setTranslation} label="Translation" />
      )}

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <>
          <div className="reader">
            {desktop && (
              <div className="reader__head">
                <div className="reader__meta">
                  <span className="reader__book">{data.book_name}</span>
                  <h2 className="reader__chapter">Chapter {data.chapter}</h2>
                </div>
                <ReadingModeSwitch value={readingMode} onChange={setReadingMode} />
              </div>
            )}
            <div
              className="reader__text"
              ref={containerRef}
              onClick={
                desktop
                  ? (e) => {
                      const el = e.target.closest('[data-ref]')
                      if (el) onFocusVerse?.(el.dataset.ref)
                    }
                  : undefined
              }
            >
              {data.verses.map((verse) => (
                <span
                  key={verse.verse}
                  id={`verse-${verse.verse}`}
                  data-ref={verse.ref}
                  className={[
                    'reader__verse',
                    verse.verse === focus && 'reader__verse--focus',
                    verse.highlighted && 'reader__verse--highlighted',
                    desktop && verse.ref === focusedRef && 'reader__verse--selected',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  style={desktop ? { cursor: 'pointer' } : undefined}
                >
                  <sup className="reader__num">{verse.verse}</sup>
                  {verse.text}
                  {verse.note_count > 0 && (
                    <span className="reader__note-dot" title={`${verse.note_count} note(s)`} />
                  )}
                  {' '}
                </span>
              ))}
            </div>
          </div>

          <div className="pager">
            <button
              type="button"
              className="pager__btn"
              disabled={!data.prev}
              onClick={() => data.prev && navigate(`read/${data.prev.book}/${data.prev.chapter}`)}
            >
              <IconChevronLeft size={16} /> {data.prev ? `${data.prev.book} ${data.prev.chapter}` : 'Start'}
            </button>
            <button
              type="button"
              className="pager__btn"
              disabled={!data.next}
              onClick={() => data.next && navigate(`read/${data.next.book}/${data.next.chapter}`)}
            >
              {data.next ? `${data.next.book} ${data.next.chapter}` : 'End'} <IconChevronRight size={16} />
            </button>
          </div>
        </>
      )}

      {selectedVerse && (
        <div className="selection-bar" role="toolbar" aria-label="Selection">
          <button
            type="button"
            className="selection-bar__btn"
            onClick={withSelection(() =>
              actions.toggleHighlight(selectedVerse.ref, selectedVerse.highlighted),
            )}
          >
            <span className="selection-bar__dot" />
            <span>Highlight</span>
          </button>
          <button
            type="button"
            className="selection-bar__btn"
            onClick={withSelection(() => actions.note(selectedVerse.ref, data.translation))}
          >
            <IconNote size={19} />
            <span>Note</span>
          </button>
          <button
            type="button"
            className="selection-bar__btn"
            onClick={withSelection(() => actions.original(selectedVerse.ref))}
          >
            <IconOriginal size={19} />
            <span>Original</span>
          </button>
          <button
            type="button"
            className="selection-bar__btn"
            onClick={withSelection(() => share(`${selectedVerse.text} — ${data.label} v${selectedVerse.verse}`))}
          >
            <IconShare size={19} />
            <span>Share</span>
          </button>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- notes */

export function NotesView({ route, navigate, actions, notesVersion, highlightsVersion, threadsVersion }) {
  const threadId = route.parts[0] === 'threads' ? route.parts[1] : null
  const [filter, setFilter] = useState('threads')
  const [createError, setCreateError] = useState(null)

  if (threadId) {
    return <ThreadDetail threadId={threadId} navigate={navigate} actions={actions} threadsVersion={threadsVersion} />
  }

  const newThread = async () => {
    const name = window.prompt('Name this thread')
    if (!name?.trim()) return
    setCreateError(null)
    try {
      const thread = await api.createThread(name.trim())
      navigate(`notes/threads/${thread.id}`)
    } catch (e) {
      setCreateError(e)
    }
  }

  return (
    <div className="view">
      <div className="section__head" style={{ marginBottom: 0 }}>
        <h1 className="serif" style={{ fontWeight: 400, fontSize: '2.1rem', margin: 0 }}>
          Notes
        </h1>
        <button
          type="button"
          className="icon-btn"
          title="New thread"
          onClick={newThread}
          style={{
            width: '2.1rem',
            height: '2.1rem',
            borderRadius: '50%',
            background: 'var(--primary)',
            color: 'var(--primary-foreground)',
          }}
        >
          +
        </button>
      </div>

      <ErrorNote error={createError} />

      <div className="chips">
        {[
          ['threads', 'Threads'],
          ['notes', 'All notes'],
          ['highlights', 'Highlights'],
        ].map(([id, label]) => (
          <button key={id} type="button" className="chip" aria-pressed={filter === id} onClick={() => setFilter(id)}>
            {label}
          </button>
        ))}
      </div>

      {filter === 'threads' && <ThreadList navigate={navigate} threadsVersion={threadsVersion} />}
      {filter === 'notes' && <NoteList actions={actions} notesVersion={notesVersion} navigate={navigate} />}
      {filter === 'highlights' && (
        <HighlightList actions={actions} highlightsVersion={highlightsVersion} navigate={navigate} />
      )}
    </div>
  )
}

function ThreadList({ navigate, threadsVersion }) {
  const { data, error, loading } = useAsync(() => api.threads(), [threadsVersion])
  const threads = data?.threads ?? []

  return (
    <>
      {loading && <Spinner label="Reading" />}
      <ErrorNote error={error} />
      {!loading && threads.length === 0 && (
        <Empty mark="No threads yet">
          <p>A thread ties several verses, words and notes together while you study.</p>
        </Empty>
      )}
      <div className="stack">
        {threads.map((thread) => (
          <Panel
            key={thread.id}
            variant="dark"
            as="button"
            className="thread-card"
            onClick={() => navigate(`notes/threads/${thread.id}`)}
          >
            <div className="panel__head" style={{ marginBottom: 0 }}>
              <p className="panel__title">{thread.name}</p>
              <span className="tag" style={{ color: 'var(--dark-primary)', flex: 'none' }}>
                {thread.item_count} {thread.item_count === 1 ? 'REF' : 'REFS'}
              </span>
            </div>
            <span className="today-card__foot">
              {thread.note_count} {thread.note_count === 1 ? 'note' : 'notes'} · updated{' '}
              {formatDate(thread.updated_at)}
            </span>
          </Panel>
        ))}
      </div>
    </>
  )
}

function ThreadDetail({ threadId, navigate, actions, threadsVersion }) {
  const { data, error, loading, reload } = useAsync(() => api.thread(threadId), [threadId, threadsVersion])

  const removeItem = async (itemId) => {
    await api.removeThreadItem(itemId)
    reload()
  }

  const remove = async () => {
    if (!window.confirm(`Delete "${data.name}"? Its notes on each verse are kept.`)) return
    await api.deleteThread(threadId)
    navigate('notes')
  }

  return (
    <div className="view">
      <div className="section__head">
        <button type="button" className="link" onClick={() => navigate('notes')}>
          ← Threads
        </button>
        {data && (
          <button type="button" className="link" onClick={remove} style={{ color: 'var(--destructive)' }}>
            Delete
          </button>
        )}
      </div>

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <>
          <h1 className="serif" style={{ fontWeight: 400, fontSize: '1.9rem', margin: 0 }}>
            {data.name}
          </h1>
          <div className="results">
            {data.items.map((item) => (
              <article key={item.id} className="result">
                <div className="result__head">
                  <button
                    type="button"
                    className="result__ref"
                    style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                    onClick={() => navigate(`read/${item.book}/${item.chapter}?v=${item.verse_start}`)}
                  >
                    {item.label}
                  </button>
                </div>
                {item.text && <p className="result__text">{item.text}</p>}
                {item.note && <p className="quote">{item.note}</p>}
                <div className="result__actions">
                  <button
                    type="button"
                    className="result__action"
                    onClick={() => navigate(`read/${item.book}/${item.chapter}?v=${item.verse_start}`)}
                  >
                    Read chapter
                  </button>
                  <button
                    type="button"
                    className="result__action result__action--quiet"
                    onClick={() => removeItem(item.id)}
                  >
                    Remove
                  </button>
                </div>
              </article>
            ))}
            {data.items.length === 0 && (
              <Empty mark="No verses yet">
                <p>Add a verse to this thread from its note editor while you're reading.</p>
              </Empty>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function NoteList({ actions, notesVersion, navigate }) {
  const [q, setQ] = useState('')
  const query = useDebounced(q, 200)
  const { data, error, loading } = useAsync(() => api.notes({ q: query }), [query, notesVersion])
  const notes = data?.notes ?? []

  return (
    <>
      <SearchField value={q} onChange={setQ} placeholder="Search your notes" />
      {loading && <Spinner label="Reading" />}
      <ErrorNote error={error} />

      {!loading && !error && notes.length === 0 && (
        <Empty mark={query ? 'No notes' : 'Nothing yet'}>
          <p>
            {query
              ? `No note mentions “${query}”.`
              : 'Notes you attach to a verse collect here, and turn up in search alongside scripture.'}
          </p>
        </Empty>
      )}

      <div className="results">
        {notes.map((note) => (
          <article key={note.id} className="result">
            <div className="result__head">
              <button
                type="button"
                className="result__ref"
                style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                onClick={() => actions.note(note.verse_ref, note.translation)}
              >
                {note.label}
              </button>
              <span className="result__kind">{formatDate(note.updated_at)}</span>
            </div>
            <p className="note-body">{note.body}</p>
            {note.verse_text && <p className="quote">{note.verse_text}</p>}
            <div className="result__actions">
              <button
                type="button"
                className="result__action"
                onClick={() => navigate(`read/${note.book}/${note.chapter}?v=${note.verse}`)}
              >
                Read chapter
              </button>
              <button
                type="button"
                className="result__action"
                onClick={() => actions.note(note.verse_ref, note.translation)}
              >
                Edit
              </button>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}

function HighlightList({ actions, highlightsVersion, navigate }) {
  const { data, error, loading } = useAsync(() => api.highlights(), [highlightsVersion])
  const highlights = data?.highlights ?? []

  return (
    <>
      {loading && <Spinner label="Reading" />}
      <ErrorNote error={error} />
      {!loading && highlights.length === 0 && (
        <Empty mark="Nothing highlighted">
          <p>Select a verse while reading and choose Highlight.</p>
        </Empty>
      )}
      <div className="results">
        {highlights.map((h) => (
          <article key={h.id} className="result">
            <div className="result__head">
              <button
                type="button"
                className="result__ref"
                style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                onClick={() => navigate(`read/${h.book}/${h.chapter}?v=${h.verse}`)}
              >
                {h.label}
              </button>
              <span className="result__kind">{formatDate(h.created_at)}</span>
            </div>
            <div className="result__actions">
              <button
                type="button"
                className="result__action result__action--quiet"
                onClick={() => actions.toggleHighlight(h.verse_ref, true)}
              >
                Remove
              </button>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}
