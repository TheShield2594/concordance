import { useEffect, useState } from 'react'

import { api } from './api.js'
import { useAsync } from './hooks.js'
import {
  IconChevronLeft,
  IconChevronRight,
  IconNote,
  IconRead,
  IconSearch,
  IconSidebar,
  IconToday,
  IconTopic,
} from './icons.jsx'
import { ComparePanel, NotesPanel, OriginalPanel } from './sheets.jsx'
import { NotesView, ReadView, SearchView, TodayView, TopicsView } from './views.jsx'

const NAV = [
  { id: 'today', label: 'Today', Icon: IconToday },
  { id: 'read', label: 'Library', Icon: IconRead },
  { id: 'notes', label: 'Notes', Icon: IconNote },
  { id: 'topics', label: 'Topics', Icon: IconTopic },
]

const RAIL_TABS = [
  { id: 'original', label: 'Original' },
  { id: 'compare', label: 'Compare' },
  { id: 'notes', label: 'Notes' },
]

/** The Mac three-column study desk: sidebar, a centred reading column, and a
 * right rail that shows Original / Compare / Notes for whichever verse was
 * last clicked -- the same information the phone reaches through sheets,
 * always on screen here because there's room for it. */
export default function Desktop(props) {
  const { route, navigate, readable, chooseReading, meta, chips, actions, threadsVersion } = props
  const [collapsed, setCollapsed] = useState(false)
  const [focusedRef, setFocusedRef] = useState(null)
  const [railTab, setRailTab] = useState('original')

  const [book, chapter] = route.tab === 'read' ? route.parts : []
  useEffect(() => setFocusedRef(null), [book, chapter])

  // The titlebar advertises ⌘K; make it true, and steal it from the
  // browser's own address-bar shortcut before that fires instead.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        navigate('search')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  const threads = useAsync(() => api.threads(), [threadsVersion])
  const books = meta?.books ?? []
  const currentBook = (book || '').toUpperCase()

  return (
    <div className="desktop">
      <div className="desktop__titlebar">
        <div className="desktop__dots">
          <span className="desktop__dot" style={{ background: '#e0685e' }} />
          <span className="desktop__dot" style={{ background: '#e5b44a' }} />
          <span className="desktop__dot" style={{ background: '#63b558' }} />
        </div>
        <div className="desktop__titlebar-tools">
          <button type="button" className="icon-btn" onClick={() => setCollapsed((c) => !c)} title="Toggle sidebar">
            <IconSidebar size={18} />
          </button>
          <button type="button" className="icon-btn" onClick={() => window.history.back()} title="Back">
            <IconChevronLeft size={16} />
          </button>
          <button type="button" className="icon-btn" onClick={() => window.history.forward()} title="Forward">
            <IconChevronRight size={16} />
          </button>
        </div>
        <div className="desktop__search">
          <button type="button" className="desktop__search-field" onClick={() => navigate('search')}>
            <IconSearch size={14} />
            Search scripture, topics, notes
            <kbd>⌘K</kbd>
          </button>
        </div>
        <div className="desktop__titlebar-tools" style={{ marginLeft: 'auto' }} />
      </div>

      <div className="desktop__body">
        {!collapsed && (
          <div className="desktop__sidebar">
            <div className="desktop__nav">
              {NAV.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="desktop__nav-item"
                  aria-current={route.tab === item.id ? 'page' : undefined}
                  onClick={() => navigate(item.id === 'read' ? 'read' : item.id)}
                >
                  <item.Icon size={16} />
                  {item.label}
                </button>
              ))}
            </div>

            {['NT', 'OT'].map((testament) => (
              <div className="desktop__nav-group" key={testament}>
                <div className="desktop__nav-heading">
                  {testament === 'NT' ? 'New Testament' : 'Old Testament'}
                </div>
                {books
                  .filter((b) => b.testament === testament)
                  .map((b) => (
                    <button
                      key={b.code}
                      type="button"
                      className="desktop__book-row"
                      aria-current={currentBook === b.code ? 'page' : undefined}
                      onClick={() => navigate(`read/${b.code}/1`)}
                    >
                      <span>{b.name}</span>
                      <span className="count">{b.chapters}</span>
                    </button>
                  ))}
              </div>
            ))}

            <div className="desktop__nav-group">
              <div className="desktop__nav-heading">Threads</div>
              {(threads.data?.threads ?? []).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="desktop__thread-row"
                  onClick={() => navigate(`notes/threads/${t.id}`)}
                >
                  <span className="dot" />
                  {t.name}
                </button>
              ))}
              {threads.data?.threads?.length === 0 && (
                <div className="desktop__nav-heading" style={{ textTransform: 'none', letterSpacing: 0 }}>
                  None yet
                </div>
              )}
            </div>

            <label className="desktop__translation">
              <span className="desktop__translation-code">{readable}</span>
              <span className="desktop__translation-note">{chips.length} translations offline</span>
              <select
                value={readable}
                onChange={(e) => chooseReading(e.target.value)}
                style={{
                  position: 'absolute',
                  inset: 0,
                  opacity: 0,
                  cursor: 'pointer',
                  width: '100%',
                }}
              >
                {chips
                  .filter((c) => c !== 'ALL')
                  .map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
              </select>
            </label>
          </div>
        )}

        <div className="desktop__main">
          {route.tab === 'read' && (
            <div className="desktop__reader">
              <ReadView
                {...props}
                desktop
                focusedRef={focusedRef}
                onFocusVerse={(ref) => {
                  setFocusedRef(ref)
                  setRailTab('original')
                }}
              />
            </div>
          )}
          {route.tab === 'today' && (
            <div className="desktop__page">
              <TodayView {...props} />
            </div>
          )}
          {route.tab === 'search' && (
            <div className="desktop__page">
              <SearchView {...props} />
            </div>
          )}
          {route.tab === 'topics' && (
            <div className="desktop__page">
              <TopicsView {...props} />
            </div>
          )}
          {route.tab === 'notes' && (
            <div className="desktop__page">
              <NotesView {...props} />
            </div>
          )}
        </div>

        {route.tab === 'read' && book && chapter && (
          <div className="desktop__rail">
            <div className="desktop__rail-tabs">
              {RAIL_TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="desktop__rail-tab"
                  aria-current={railTab === t.id}
                  onClick={() => setRailTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="desktop__rail-body">
              {!focusedRef && (
                <p className="muted">Click a verse to study its original language, cross-references and notes.</p>
              )}
              {focusedRef && railTab === 'original' && (
                <div className="original">
                  <OriginalPanel verseRef={focusedRef} translation={readable} onStrongs={actions.strongs} />
                </div>
              )}
              {focusedRef && railTab === 'compare' && (
                <ComparePanel
                  verseRef={focusedRef}
                  translation={readable}
                  onRead={(b, c, v) => navigate(`read/${b}/${c}?v=${v}`)}
                  onTopic={(id) => navigate(`topics/${id}`)}
                />
              )}
              {focusedRef && railTab === 'notes' && (
                <NotesPanel
                  verseRef={focusedRef}
                  translation={readable}
                  onChanged={props.bumpNotes}
                  onThreadsChanged={() => threads.reload()}
                  onRead={(ref) => {
                    const [b, c, v] = ref.split('.')
                    navigate(`read/${b}/${c}${v ? `?v=${v}` : ''}`)
                  }}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
