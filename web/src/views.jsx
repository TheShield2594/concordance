import { useEffect, useMemo, useState } from 'react'

import { api } from './api.js'
import {
  CallNumber,
  Chips,
  Empty,
  ErrorNote,
  Marked,
  SearchField,
  Section,
  Spinner,
  TopicRow,
  VerseCard,
} from './components.jsx'
import { formatDate } from './format.js'
import { useAsync, useDebounced } from './hooks.js'

const PAGE = 25

/* ------------------------------------------------------------------ search */

export function SearchView({ route, navigate, translation, setTranslation, chips, actions }) {
  const [q, setQ] = useState(route.query.q ?? '')
  const query = useDebounced(q, 200)
  const [extra, setExtra] = useState([])
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState(null)
  // Best match first, or straight through Genesis to Revelation.
  const [sort, setSort] = useState('relevance')

  // Keep the URL in step so a reload, or a trip through another tab, returns
  // to the same search. Goes through navigate so the route state stays true.
  useEffect(() => {
    navigate(query ? `search?q=${encodeURIComponent(query)}` : 'search', {
      replace: true,
    })
  }, [query, navigate])

  const { data, error, loading } = useAsync(
    () => api.search({ q: query, translation, limit: PAGE, sort }),
    [query, translation, sort],
    { skip: !query.trim() },
  )

  useEffect(() => setExtra([]), [query, translation, sort])

  const verses = useMemo(() => [...(data?.verses ?? []), ...extra], [data, extra])
  const more = data ? verses.length < data.verse_total : false

  const loadMore = async () => {
    setLoadingMore(true)
    setMoreError(null)
    try {
      const next = await api.search({
        q: query,
        translation,
        limit: PAGE,
        offset: verses.length,
        include: 'verses',
        sort,
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
      <SearchField
        value={q}
        onChange={setQ}
        placeholder="Search scripture, topics and notes"
        autoFocus
      />
      <Chips
        options={chips}
        value={translation}
        onChange={setTranslation}
        label="Translation"
      />

      {!query.trim() && (
        <Empty mark="Concordance">
          <p>
            Search the text of four translations, the topics of Nave's, and your own
            notes — all at once.
          </p>
          <p>
            A reference — John 3:16, PHP.4.6 — or a Strong's number jumps straight
            to it.
          </p>
        </Empty>
      )}

      {loading && <Spinner />}
      <ErrorNote error={error} />

      {data?.reference && (
        <ReferenceCard
          reference={data.reference}
          navigate={navigate}
          actions={actions}
        />
      )}

      {data?.strongs && (
        <Section title="Original language" aside={data.strongs.language}>
          <button
            type="button"
            className="card card--strongs"
            onClick={() => actions.strongs(data.strongs.id)}
          >
            <span className="card__head">
              <span className="callno">{data.strongs.id}</span>
              <span className="tag">{data.strongs.translit}</span>
              <span className="tag" style={{ marginLeft: 'auto' }}>
                {data.strongs.occurrences.toLocaleString()}×
              </span>
            </span>
            <span className={`lemma lemma--${data.strongs.lang}`} dir={data.strongs.direction}>
              {data.strongs.lemma}
            </span>
            <span className="card__text">{data.strongs.definition}</span>
            <span className="card__actions">
              <span className="action">Every occurrence →</span>
            </span>
          </button>
        </Section>
      )}

      {data?.topics?.length > 0 && (
        <Section title="Topics" aside={`${data.topics.length} matching`}>
          <div className="stack">
            {data.topics.map((topic) => (
              <TopicRow
                key={topic.id}
                topic={topic}
                onOpen={(t) => navigate(`topics/${t.id}`)}
              />
            ))}
          </div>
        </Section>
      )}

      {data?.notes?.length > 0 && (
        <Section title="Your notes" aside={`${data.notes.length}`}>
          <div className="stack">
            {data.notes.map((note) => (
              <article key={note.id} className="card card--verdigris">
                <div className="card__head">
                  <CallNumber onClick={() => actions.note(note.verse_ref)}>
                    {note.verse_ref}
                  </CallNumber>
                  <span className="tag">Note</span>
                </div>
                <p className="note-body">
                  <Marked segments={note.segments} text={note.body} />
                </p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {data && !(data.verse_total === 0 && (data.strongs || data.reference)) && (
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
                  onClick={() =>
                    setSort(sort === 'relevance' ? 'canonical' : 'relevance')
                  }
                  title="Switch between best-match and Genesis-to-Revelation order"
                >
                  {sort === 'relevance' ? 'By relevance' : 'In order'}
                </button>
              </>
            ) : undefined
          }
        >
          {/* A Strong's number or a verse reference never appears in the
              English text, so its search finds no verses by design. Saying
              "nothing matched" over a card that plainly matched something
              reads as a failure. */}
          {data.verse_total === 0 && !loading && !data.strongs && !data.reference ? (
            <Empty mark="No verses">
              <p>Nothing matched “{query}”.</p>
            </Empty>
          ) : (
            <div className="stack">
              {verses.map((verse) => (
                <VerseCard
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
                <button
                  type="button"
                  className="btn"
                  onClick={loadMore}
                  disabled={loadingMore}
                >
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

/**
 * The verse a reference-shaped search names, set above the text hits the way
 * a Strong's entry is. A whole-chapter reference is a doorway with no text;
 * a verse or range brings its text along, one line per translation on file.
 */
function ReferenceCard({ reference, navigate, actions }) {
  const single = reference.verse_start > 0
  const range = reference.verse_end > reference.verse_start
  const firstRef = `${reference.book}.${reference.chapter}.${reference.verse_start}`
  const read = () =>
    navigate(
      `read/${reference.book}/${reference.chapter}${
        single ? `?v=${reference.verse_start}` : ''
      }`,
    )

  return (
    <Section title="Reference" aside={reference.book_name}>
      <article className="card">
        <div className="card__head">
          <CallNumber onClick={read} title={`Read ${reference.label}`}>
            {reference.ref}
          </CallNumber>
          <span className="tag">{reference.label}</span>
        </div>
        {reference.verses.length > 0 && (
          <div className="stack">
            {reference.verses.map((verse) => (
              <p key={`${verse.translation}-${verse.id}`} className="card__text">
                {verse.text}{' '}
                <span className="tag">
                  {range ? `v${verse.verse} · ` : ''}
                  {verse.translation}
                </span>
              </p>
            ))}
          </div>
        )}
        <div className="card__actions">
          <button type="button" className="action" onClick={read}>
            Read chapter
          </button>
          {single && (
            <>
              <button
                type="button"
                className="action action--verdigris"
                onClick={() => actions.note(firstRef)}
              >
                Add note
              </button>
              <button
                type="button"
                className="action action--verdigris"
                onClick={() => actions.crossRefs(firstRef)}
              >
                Cross-refs
              </button>
              <button
                type="button"
                className="action"
                onClick={() => actions.original(firstRef)}
              >
                Original
              </button>
            </>
          )}
        </div>
      </article>
    </Section>
  )
}

/* ------------------------------------------------------------------ topics */

export function TopicsView({ route, navigate, readable, actions }) {
  const topicId = route.parts[0]
  if (topicId) {
    return (
      <TopicDetail
        topicId={topicId}
        navigate={navigate}
        readable={readable}
        actions={actions}
      />
    )
  }
  return <TopicList navigate={navigate} />
}

function TopicList({ navigate }) {
  const [q, setQ] = useState('')
  const query = useDebounced(q, 200)
  const { data, error, loading } = useAsync(() => api.topics({ q: query }), [query])

  return (
    <div className="view">
      <SearchField value={q} onChange={setQ} placeholder="Search Nave's topics" />
      {loading && <Spinner label="Looking up" />}
      <ErrorNote error={error} />
      <Section
        title={query ? 'Matching topics' : 'Largest topics'}
        aside={data ? `${data.topics.length}` : undefined}
      >
        <div className="stack">
          {data?.topics?.map((topic) => (
            <TopicRow
              key={topic.id}
              topic={topic}
              onOpen={(t) => navigate(`topics/${t.id}`)}
            />
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
  const { data, error, loading } = useAsync(
    () => api.topic(topicId, readable),
    [topicId, readable],
  )

  // A reference that names a verse takes the reader to it; a whole-chapter
  // reference just opens the chapter.
  const readTarget = (ref) =>
    `read/${ref.book}/${ref.chapter}${
      ref.verse_start > 0 ? `?v=${ref.verse_start}` : ''
    }`

  return (
    <div className="view">
      <div className="section__head">
        <button type="button" className="link" onClick={() => navigate('topics')}>
          ← All topics
        </button>
        <span className="tag tag--onink">
          {data ? `${data.ref_count} refs · ${data.translation}` : ''}
        </span>
      </div>

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <>
          <h2 style={{ fontFamily: 'var(--display)', margin: 0 }}>{data.name}</h2>
          {data.groups.map((group, i) => (
            <Section key={i} title={group.heading || 'References'}>
              <div className="stack">
                {group.refs.map((ref, j) => (
                  <article key={`${ref.ref}-${j}`} className="card">
                    <div className="card__head">
                      <CallNumber onClick={() => navigate(readTarget(ref))}>
                        {ref.ref}
                      </CallNumber>
                      <span className="tag">{ref.label}</span>
                    </div>
                    {ref.text && <p className="card__text">{ref.text}</p>}
                    <div className="card__actions">
                      <button
                        type="button"
                        className="action"
                        onClick={() => navigate(readTarget(ref))}
                      >
                        Read chapter
                      </button>
                      {ref.verse_start > 0 && (
                        <button
                          type="button"
                          className="action action--verdigris"
                          onClick={() =>
                            actions.note(
                              `${ref.book}.${ref.chapter}.${ref.verse_start}`,
                              data.translation,
                            )
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

export function ReadView({ route, navigate, readable, chooseReading, meta, actions, notesVersion }) {
  const [book, chapter] = route.parts
  const chips = (meta?.translation_chips ?? []).filter((t) => t !== 'ALL')

  if (!book) return <BookPicker meta={meta} navigate={navigate} />
  if (!chapter)
    return <ChapterPicker meta={meta} book={book} navigate={navigate} />

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
    />
  )
}

function BookPicker({ meta, navigate }) {
  const books = meta?.books ?? []
  return (
    <div className="view">
      {['OT', 'NT'].map((testament) => (
        <Section
          key={testament}
          title={testament === 'OT' ? 'Old Testament' : 'New Testament'}
        >
          <div className="grid grid--books">
            {books
              .filter((b) => b.testament === testament)
              .map((b) => (
                <button
                  key={b.code}
                  type="button"
                  className="tile"
                  onClick={() => navigate(`read/${b.code}`)}
                >
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
        <CallNumber onInk>{book.toUpperCase()}</CallNumber>
      </div>
      <Section title={info ? info.name : book} aside={`${count} chapters`}>
        <div className="grid grid--chapters">
          {Array.from({ length: count }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              className="tile"
              onClick={() => navigate(`read/${book.toUpperCase()}/${n}`)}
            >
              {n}
            </button>
          ))}
        </div>
      </Section>
    </div>
  )
}

function Chapter({
  book,
  chapter,
  focus,
  translation,
  setTranslation,
  chips,
  navigate,
  actions,
  notesVersion,
}) {
  const { data, error, loading } = useAsync(
    () => api.chapter(book, chapter, translation),
    [book, chapter, translation, notesVersion],
  )

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [book, chapter])

  // A link that named a verse carries the reader down to it once the chapter
  // arrives; the wash that marks it is the --focus class on the verse itself.
  useEffect(() => {
    if (!data || !focus) return
    document
      .getElementById(`verse-${focus}`)
      ?.scrollIntoView({ block: 'center' })
  }, [data, focus])

  return (
    <div className="view">
      <div className="section__head">
        <button
          type="button"
          className="link"
          onClick={() => navigate(`read/${book.toUpperCase()}`)}
        >
          ← Chapters
        </button>
        <CallNumber onInk large>
          {book.toUpperCase()}.{chapter}
        </CallNumber>
      </div>

      <Chips
        options={chips}
        value={translation}
        onChange={setTranslation}
        label="Translation"
      />

      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <>
          <div className="reader">
            <h2>{data.label}</h2>
            <div className="tag" style={{ marginBottom: '0.9rem' }}>
              {data.translation} · {data.verses.length} verses
            </div>
            {/* Two gestures per verse: the number opens the original, the
                text opens notes. The paragraph itself is no longer the
                control, so neither one sits inside the other. */}
            {data.verses.map((verse) => (
              <p
                key={verse.verse}
                id={`verse-${verse.verse}`}
                className={
                  verse.verse === focus
                    ? 'reader__verse reader__verse--focus'
                    : 'reader__verse'
                }
              >
                <button
                  type="button"
                  className="reader__num"
                  onClick={() => actions.original(verse.ref)}
                  title="The Hebrew, Aramaic or Greek behind this verse"
                >
                  {verse.verse}
                </button>
                <span
                  className="reader__body"
                  role="button"
                  tabIndex={0}
                  onClick={() => actions.note(verse.ref, data.translation)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      actions.note(verse.ref, data.translation)
                    }
                  }}
                  title="Add or read notes on this verse"
                >
                  {verse.text}
                  {verse.note_count > 0 && (
                    <span
                      className="reader__note-dot"
                      title={`${verse.note_count} note(s)`}
                    />
                  )}
                </span>
              </p>
            ))}
          </div>

          <div className="pager">
            <button
              type="button"
              className="btn"
              disabled={!data.prev}
              onClick={() =>
                data.prev && navigate(`read/${data.prev.book}/${data.prev.chapter}`)
              }
            >
              ←{' '}
              {data.prev ? (
                <CallNumber onInk>
                  {data.prev.book}.{data.prev.chapter}
                </CallNumber>
              ) : (
                'Start'
              )}
            </button>
            <button
              type="button"
              className="btn"
              disabled={!data.next}
              onClick={() =>
                data.next && navigate(`read/${data.next.book}/${data.next.chapter}`)
              }
            >
              {data.next ? (
                <CallNumber onInk>
                  {data.next.book}.{data.next.chapter}
                </CallNumber>
              ) : (
                'End'
              )}{' '}
              →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- notes */

export function NotesView({ navigate, actions, notesVersion }) {
  const [q, setQ] = useState('')
  const query = useDebounced(q, 200)
  const { data, error, loading } = useAsync(
    () => api.notes({ q: query }),
    [query, notesVersion],
  )
  const notes = data?.notes ?? []

  return (
    <div className="view">
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

      <div className="stack">
        {notes.map((note) => (
          <article key={note.id} className="card card--verdigris">
            <div className="card__head">
              <CallNumber onClick={() => actions.note(note.verse_ref, note.translation)}>
                {note.verse_ref}
              </CallNumber>
              <span className="tag">{note.label}</span>
              <span className="tag" style={{ marginLeft: 'auto' }}>
                {formatDate(note.updated_at)}
              </span>
            </div>
            <p className="note-body">{note.body}</p>
            {note.verse_text && <p className="quote">{note.verse_text}</p>}
            <div className="card__actions">
              <button
                type="button"
                className="action"
                onClick={() =>
                  navigate(`read/${note.book}/${note.chapter}?v=${note.verse}`)
                }
              >
                Read chapter
              </button>
              <button
                type="button"
                className="action action--verdigris"
                onClick={() => actions.note(note.verse_ref, note.translation)}
              >
                Edit
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
