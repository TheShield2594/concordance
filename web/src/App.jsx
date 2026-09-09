import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from './api.js'
import { ErrorNote, Spinner } from './components.jsx'
import Desktop from './desktop.jsx'
import { IconNote, IconRead, IconSearch, IconToday } from './icons.jsx'
import { useAsync, useMediaQuery, useRoute, useStoredState } from './hooks.js'
import { CrossRefSheet, InterlinearSheet, NoteSheet, StrongsSheet } from './sheets.jsx'
import { NotesView, ReadView, SearchView, TodayView, TopicsView } from './views.jsx'

const TABS = [
  { id: 'today', label: 'Today', Icon: IconToday },
  { id: 'read', label: 'Read', Icon: IconRead },
  { id: 'search', label: 'Search', Icon: IconSearch },
  { id: 'notes', label: 'Notes', Icon: IconNote },
]

export default function App() {
  const [route, navigate] = useRoute()
  const isDesktop = useMediaQuery('(min-width: 68rem)')
  const prefersDark = useMediaQuery('(prefers-color-scheme: dark)')
  // day | auto | night, for the reading surface only. Everywhere else follows
  // the system, always.
  const [readingMode, setReadingMode] = useStoredState('concordance.readingMode', 'auto')
  const [translation, setTranslation] = useStoredState('concordance.translation', 'ALL')
  // The reader has to name one translation. Keeping that choice separate means
  // a search filtered across ALL stays ALL when you go read something.
  const [reading, setReading] = useStoredState('concordance.reading', 'KJV')
  const meta = useAsync(() => api.meta(), [])

  // The reader is the only screen that gets its own palette, and it gets the
  // whole shell with it: a parchment tab bar under a dark reading column looks
  // like a bug. `night` carries a full token set of its own, so nothing here
  // ever leaves both classes on at once -- and because the inline script in
  // index.html keeps writing `dark` on every system change, this reasserts the
  // choice whenever that preference moves.
  useEffect(() => {
    const mode = route.tab === 'read' ? readingMode : 'auto'
    const root = document.documentElement
    root.classList.toggle('night', mode === 'night')
    root.classList.toggle('dark', mode === 'auto' && prefersDark)
  }, [route.tab, readingMode, prefersDark])

  // Sheets: one note editor and one cross-reference panel at a time.
  const [noteSheet, setNoteSheet] = useState(null)
  const [crossSheet, setCrossSheet] = useState(null)
  const [originalSheet, setOriginalSheet] = useState(null)
  // A Strong's entry can be reached from a word in the interlinear or straight
  // from a search. It remembers which verse it came from, if any, so the way
  // back is a link rather than a second modal stacked on the first.
  const [strongsSheet, setStrongsSheet] = useState(null)
  // Bumped whenever notes, highlights or threads change, so open views refetch.
  const [notesVersion, setNotesVersion] = useState(0)
  const [highlightsVersion, setHighlightsVersion] = useState(0)
  const [threadsVersion, setThreadsVersion] = useState(0)

  const bumpNotes = useCallback(() => setNotesVersion((n) => n + 1), [])
  const bumpHighlights = useCallback(() => setHighlightsVersion((n) => n + 1), [])
  const bumpThreads = useCallback(() => setThreadsVersion((n) => n + 1), [])

  // A note (or a highlight, or a thread add) opened without a translation
  // takes the one currently on screen, not a hardcoded KJV; the ALL case is
  // resolved to `readable` below.
  const actions = {
    note: useCallback(
      (ref, forTranslation) =>
        setNoteSheet({ ref, translation: forTranslation || translation }),
      [translation],
    ),
    crossRefs: useCallback((ref) => setCrossSheet({ ref }), []),
    original: useCallback((ref) => setOriginalSheet({ ref }), []),
    strongs: useCallback((number) => setStrongsSheet({ number }), []),
    toggleHighlight: useCallback(
      async (ref, isHighlighted) => {
        try {
          if (isHighlighted) await api.removeHighlight(ref)
          else await api.addHighlight(ref)
          bumpHighlights()
        } catch (e) {
          // The selection bar fires this without awaiting it, so a failure
          // has to say something itself rather than becoming a silent
          // unhandled rejection the user never sees.
          window.alert(`Couldn't update the highlight: ${e.message}`)
        }
      },
      [bumpHighlights],
    ),
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
    chips,
    actions,
    notesVersion,
    highlightsVersion,
    threadsVersion,
    bumpNotes,
    readingMode,
    setReadingMode,
  }

  const sheets = (
    <>
      {noteSheet && (
        <NoteSheet
          verseRef={noteSheet.ref}
          translation={noteSheet.translation === 'ALL' ? readable : noteSheet.translation}
          onClose={() => setNoteSheet(null)}
          onChanged={bumpNotes}
          onThreadsChanged={bumpThreads}
          onRead={(ref) => {
            const [book, chapter, verse] = ref.split('.')
            setNoteSheet(null)
            navigate(`read/${book}/${chapter}${verse ? `?v=${verse}` : ''}`)
          }}
        />
      )}

      {originalSheet && (
        <InterlinearSheet
          verseRef={originalSheet.ref}
          translation={readable}
          onClose={() => setOriginalSheet(null)}
          onStrongs={(number) => {
            setOriginalSheet(null)
            setStrongsSheet({ number, from: originalSheet.ref })
          }}
        />
      )}

      {strongsSheet && (
        <StrongsSheet
          number={strongsSheet.number}
          translation={readable}
          onClose={() => setStrongsSheet(null)}
          onBack={
            strongsSheet.from
              ? () => {
                  setStrongsSheet(null)
                  setOriginalSheet({ ref: strongsSheet.from })
                }
              : undefined
          }
          backLabel={strongsSheet.from}
          onRead={(book, chapter, verse) => {
            setStrongsSheet(null)
            navigate(`read/${book}/${chapter}${verse ? `?v=${verse}` : ''}`)
          }}
        />
      )}

      {crossSheet && (
        <CrossRefSheet
          verseRef={crossSheet.ref}
          translation={readable}
          onClose={() => setCrossSheet(null)}
          onRead={(book, chapter, verse) => {
            setCrossSheet(null)
            navigate(`read/${book}/${chapter}${verse ? `?v=${verse}` : ''}`)
          }}
          onTopic={(id) => {
            setCrossSheet(null)
            navigate(`topics/${id}`)
          }}
        />
      )}
    </>
  )

  if (meta.loading || meta.error) {
    return (
      <div className="app">
        <div className="view">
          {meta.loading && <Spinner label="Opening the stacks" />}
          <ErrorNote error={meta.error} />
        </div>
      </div>
    )
  }

  if (isDesktop) {
    return (
      <div className="app">
        <Desktop {...shared} />
        {sheets}
      </div>
    )
  }

  return (
    <div className="app">
      <div className="shell">
        {route.tab === 'today' && <TodayView {...shared} />}
        {route.tab === 'search' && <SearchView {...shared} />}
        {route.tab === 'topics' && <TopicsView {...shared} />}
        {route.tab === 'read' && <ReadView {...shared} />}
        {route.tab === 'notes' && <NotesView {...shared} />}
      </div>

      <nav className="tabs" aria-label="Sections">
        <div className="tabs__inner">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className="tab"
              aria-current={route.tab === tab.id ? 'page' : undefined}
              onClick={() => navigate(tab.id === 'search' ? lastSearch.current : tab.id)}
            >
              <span className="tab__glyph">
                <tab.Icon size={23} />
              </span>
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      {sheets}
    </div>
  )
}
