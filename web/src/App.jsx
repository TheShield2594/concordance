import { useCallback, useState } from 'react'

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
  const meta = useAsync(() => api.meta(), [])

  // Sheets: one note editor and one cross-reference panel at a time.
  const [noteSheet, setNoteSheet] = useState(null)
  const [crossSheet, setCrossSheet] = useState(null)
  // Bumped whenever notes change, so open views refetch.
  const [notesVersion, setNotesVersion] = useState(0)

  const actions = {
    note: useCallback(
      (ref, forTranslation) =>
        setNoteSheet({ ref, translation: forTranslation || 'KJV' }),
      [],
    ),
    crossRefs: useCallback((ref) => setCrossSheet({ ref }), []),
  }

  const chips = meta.data?.translation_chips ?? ['ALL', 'KJV', 'ASV', 'WEB', 'BSB']
  const readable = translation === 'ALL' ? 'KJV' : translation

  const shared = {
    route,
    navigate,
    translation,
    setTranslation,
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
              onClick={() => navigate(tab.id)}
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
