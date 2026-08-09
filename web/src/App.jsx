import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from './api.js'
import { ErrorNote, Spinner } from './components.jsx'
import { useAsync, useRoute, useStoredState } from './hooks.js'
import { CrossRefSheet, NoteSheet } from './sheets.jsx'
import { NotesView, ReadView, SearchView, TopicsView } from './views.jsx'

// Typographic marks, not emoji -- the chrome stays monochrome parchment.
const TABS = [
  { id: 'search', label: 'Search', glyph: '⌕' },
  { id: 'topics', label: 'Topics', glyph: '☰' },
  { id: 'read', label: 'Read', glyph: '▤' },
  { id: 'notes', label: 'Notes', glyph: '✎' },
]

const SUBTITLE = {
  search: 'Full text · four translations',
  topics: "Nave's topical index",
  read: 'Chapter in context',
  notes: 'Your marginalia',
}

export default function App() {
  const [route, navigate] = useRoute()
  const [translation, setTranslation] = useStoredState('concordance.translation', 'ALL')
  // The reader has to name one translation. Keeping that choice separate means
  // a search filtered across ALL stays ALL when you go read something.
  const [reading, setReading] = useStoredState('concordance.reading', 'KJV')
  const meta = useAsync(() => api.meta(), [])

  // Sheets: one note editor and one cross-reference panel at a time.
  const [noteSheet, setNoteSheet] = useState(null)
  const [crossSheet, setCrossSheet] = useState(null)
  // Bumped whenever notes change, so open views refetch.
  const [notesVersion, setNotesVersion] = useState(0)

  // A note opened without a translation takes the one currently on screen,
  // not a hardcoded KJV; the ALL case is resolved to `readable` below.
  const actions = {
    note: useCallback(
      (ref, forTranslation) =>
        setNoteSheet({ ref, translation: forTranslation || translation }),
      [translation],
    ),
    crossRefs: useCallback((ref) => setCrossSheet({ ref }), []),
  }

  // Coming back to the Search tab should land on the search you left, not an
  // empty box, so remember where that tab was.
  const lastSearch = useRef('search')
  useEffect(() => {
    if (route.tab === 'search')
      lastSearch.current = route.query.q
        ? `search?q=${encodeURIComponent(route.query.q)}`
        : 'search'
  }, [route])

  const chips = meta.data?.translation_chips ?? ['ALL', 'KJV', 'ASV', 'WEB', 'BSB']
  const readable = translation === 'ALL' ? reading : translation

  // A code left in localStorage that the database no longer carries would
  // filter every search down to nothing, so drop back to something real.
  useEffect(() => {
    const available = meta.data?.translation_chips
    if (!available) return
    if (!available.includes(translation)) setTranslation('ALL')
    if (!available.includes(reading))
      setReading(available.find((t) => t !== 'ALL') ?? 'KJV')
  }, [meta.data, translation, reading, setTranslation, setReading])

  // Picking a translation in the reader records a reading choice. It only
  // rewrites the search filter when that filter already names one translation.
  const chooseReading = useCallback(
    (code) => {
      setReading(code)
      if (translation !== 'ALL') setTranslation(code)
    },
    [translation, setReading, setTranslation],
  )

  const shared = {
    route,
    navigate,
    translation,
    setTranslation,
    readable,
    chooseReading,
    meta: meta.data,
    actions,
    notesVersion,
  }

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead__row">
          <h1>Concordance</h1>
          <span className="masthead__sub">{SUBTITLE[route.tab] ?? ''}</span>
        </div>
      </header>

      {meta.loading && <Spinner label="Opening the stacks" />}
      <ErrorNote error={meta.error} />

      {meta.data && route.tab === 'search' && <SearchView {...shared} chips={chips} />}
      {meta.data && route.tab === 'topics' && <TopicsView {...shared} />}
      {meta.data && route.tab === 'read' && <ReadView {...shared} />}
      {meta.data && route.tab === 'notes' && <NotesView {...shared} />}

      <nav className="tabs" aria-label="Sections">
        <div className="tabs__inner">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className="tab"
              aria-current={route.tab === tab.id ? 'page' : undefined}
              onClick={() =>
                navigate(tab.id === 'search' ? lastSearch.current : tab.id)
              }
            >
              <span className="tab__glyph" aria-hidden="true">
                {tab.glyph}
              </span>
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {noteSheet && (
        <NoteSheet
          verseRef={noteSheet.ref}
          translation={
            noteSheet.translation === 'ALL' ? readable : noteSheet.translation
          }
          onClose={() => setNoteSheet(null)}
          onChanged={() => setNotesVersion((n) => n + 1)}
          onRead={(ref) => {
            const [book, chapter] = ref.split('.')
            setNoteSheet(null)
            navigate(`read/${book}/${chapter}`)
          }}
        />
      )}

      {crossSheet && (
        <CrossRefSheet
          verseRef={crossSheet.ref}
          translation={readable}
          onClose={() => setCrossSheet(null)}
          onRead={(book, chapter) => {
            setCrossSheet(null)
            navigate(`read/${book}/${chapter}`)
          }}
          onTopic={(id) => {
            setCrossSheet(null)
            navigate(`topics/${id}`)
          }}
        />
      )}
    </div>
  )
}
