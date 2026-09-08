import { useEffect, useRef, useState } from 'react'

import { api } from './api.js'
import { Badge, ErrorNote, Panel, Sheet, Spinner } from './components.jsx'
import { formatDateTime } from './format.js'
import { useAsync } from './hooks.js'

/** Attach or edit notes on a verse, and file it into a study thread. */
/** Note editor + thread picker for one verse -- the body shared by the
 * mobile Note sheet and the desktop rail's Notes tab. */
export function NotesPanel({ verseRef, translation, onChanged, onThreadsChanged, onRead }) {
  const verse = useAsync(() => api.verse(verseRef, translation), [verseRef, translation])
  const notes = useAsync(() => api.notes({ ref: verseRef }), [verseRef])
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState(null) // { id, body }
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const editor = useRef(null)

  const refresh = () => {
    notes.reload()
    onChanged?.()
  }

  const save = async () => {
    const body = editing ? editing.body : draft
    if (!body.trim()) return
    setBusy(true)
    setError(null)
    try {
      if (editing) {
        await api.updateNote(editing.id, body)
        setEditing(null)
      } else {
        await api.createNote({ verse_ref: verseRef, body, translation })
        setDraft('')
      }
      refresh()
      editor.current?.focus()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete this note? It cannot be recovered.')) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteNote(id)
      if (editing?.id === id) setEditing(null)
      refresh()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const text = verse.data?.verses?.[0]?.text
  const existing = notes.data?.notes ?? []

  return (
    <>
      {text && <p className="quote">{text}</p>}
      <ErrorNote error={verse.error} />
      <ErrorNote error={notes.error} />

      <textarea
        ref={editor}
        value={editing ? editing.body : draft}
        onChange={(e) =>
          editing ? setEditing({ ...editing, body: e.target.value }) : setDraft(e.target.value)
        }
        placeholder={editing ? 'Edit note…' : 'Write a note on this verse…'}
        aria-label="Note text"
      />

      <ErrorNote error={error} />

      <div className="btn-row">
        {editing && (
          <button type="button" className="btn" onClick={() => setEditing(null)}>
            Cancel edit
          </button>
        )}
        <button type="button" className="link" onClick={() => onRead?.(verseRef)}>
          Read chapter
        </button>
        <button
          type="button"
          className="btn btn--primary"
          onClick={save}
          disabled={busy || !(editing ? editing.body : draft).trim()}
        >
          {editing ? 'Save note' : 'Add note'}
        </button>
      </div>

      <AddToThread verseRef={verseRef} onChanged={onThreadsChanged} />

      {notes.loading && <Spinner label="Reading notes" />}

      {!notes.loading && existing.length > 0 && (
        <div className="results">
          {existing.map((note) => (
            <article key={note.id} className="result">
              <div className="result__head">
                <span className="result__ref">{note.verse_ref}</span>
                <span className="result__kind">{formatDateTime(note.updated_at)}</span>
              </div>
              <p className="note-body">{note.body}</p>
              <div className="result__actions">
                <button
                  type="button"
                  className="result__action"
                  onClick={() => setEditing({ id: note.id, body: note.body })}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="result__action result__action--quiet"
                  onClick={() => remove(note.id)}
                  disabled={busy}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  )
}

export function NoteSheet({ verseRef, translation, onClose, onChanged, onThreadsChanged, onRead }) {
  const heading = useAsync(() => api.verse(verseRef, translation), [verseRef, translation])
  return (
    <Sheet eyebrow={`${verseRef} · ${translation}`} title={heading.data?.label ?? 'Note'} onClose={onClose}>
      <NotesPanel
        verseRef={verseRef}
        translation={translation}
        onChanged={onChanged}
        onThreadsChanged={onThreadsChanged}
        onRead={onRead}
      />
    </Sheet>
  )
}

/** The study-thread picker: existing threads a verse can join, plus "New…". */
export function AddToThread({ verseRef, onChanged }) {
  const { data, reload } = useAsync(() => api.threads(verseRef), [verseRef])
  const [busy, setBusy] = useState(false)
  const threads = data?.threads ?? []

  const addTo = async (id) => {
    setBusy(true)
    try {
      await api.addThreadItem(id, { verseRef })
      reload()
      onChanged?.()
    } catch {
      /* likely already a member -- the chip already shows that state */
    } finally {
      setBusy(false)
    }
  }

  const createAndAdd = async () => {
    const name = window.prompt('Name this thread')
    if (!name?.trim()) return
    setBusy(true)
    try {
      const thread = await api.createThread(name.trim())
      await api.addThreadItem(thread.id, { verseRef })
      reload()
      onChanged?.()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack stack--tight">
      <span className="quote__label muted">Add to thread</span>
      <div className="thread-add">
        {threads.map((t) => (
          <button
            key={t.id}
            type="button"
            className="thread-add__existing"
            aria-pressed={t.contains}
            disabled={busy || t.contains}
            onClick={() => addTo(t.id)}
          >
            <span className="dot" />
            {t.name}
          </button>
        ))}
        <button type="button" className="chip chip--dashed" onClick={createAndAdd} disabled={busy}>
          New…
        </button>
      </div>
    </div>
  )
}

/**
 * The verse's original language, one word at a time. The words are not
 * aligned to the English -- no public dataset lines up these translations
 * word for word -- so tapping through the strip studies one word against
 * the whole verse rather than pretending to point at an English match.
 *
 * Used two ways: as the body of the mobile Original sheet (dark chrome) and,
 * unwrapped, as the desktop rail's Original tab (light chrome) -- the CSS
 * under `.original` reads its colours from `--orig-*` variables that the
 * rail redefines, so the same markup serves both without a second copy.
 */
export function OriginalPanel({ verseRef, translation, onStrongs }) {
  const { data, error, loading } = useAsync(
    () => api.interlinear(verseRef, translation),
    [verseRef, translation],
  )
  const words = data?.words ?? []
  const [index, setIndex] = useState(0)

  useEffect(() => {
    // Land on the first word actually in the dictionary, not a prefix.
    const first = words.findIndex((w) => w.in_dictionary)
    setIndex(first === -1 ? 0 : first)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const word = words[index]
  const entry = useAsync(
    () => (word?.in_dictionary ? api.strongs(word.strongs_base) : Promise.resolve(null)),
    [word?.strongs_base],
    { skip: !word?.in_dictionary },
  )

  return (
    <>
      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data && (
        <p className="sheet__eyebrow" style={{ margin: '-0.4rem 0 0' }}>
          {data.language} · {data.label}
        </p>
      )}

      {data && words.length === 0 && (
        <p className="original__variant-note">
          No tagged original for this verse. The Hebrew and Greek follow the versification of
          English Bibles, and a few verses divide differently.
        </p>
      )}

      {words.length > 0 && (
        <div className="original">
          <div className="original__strip" dir={data.direction}>
            {words.map((w, i) => (
              <button
                key={`${w.verse}-${w.seq}`}
                type="button"
                dir="ltr"
                className="original__word"
                aria-current={i === index}
                onClick={() => setIndex(i)}
              >
                <span className={`original__word-surface original__word-surface--${w.lang}`} dir={data.direction}>
                  {w.surface}
                </span>
                <span className="original__word-translit">{w.translit}</span>
                <span className="original__word-gloss">{w.gloss}</span>
              </button>
            ))}
          </div>

          {word && !word.in_dictionary && (
            <p className="original__variant-note">
              A prefix or suffix; Strong's never numbered these.
            </p>
          )}

          {entry.loading && <Spinner label="Looking up" />}

          {word?.in_dictionary && entry.data && (
            <div className="original__detail">
              <div className="original__detail-head">
                <span className={`original__lemma original__lemma--${entry.data.lang}`} dir={entry.data.direction}>
                  {entry.data.lemma}
                </span>
                <Badge tone="onprimary" onClick={() => onStrongs(entry.data.id)}>
                  {entry.data.id}
                </Badge>
              </div>
              <p className="original__gloss">{entry.data.definition}</p>
              <div className="original__facts">
                <div className="original__fact">
                  <span className="original__fact-label">Form</span>
                  <span className="original__fact-value">{word.parsing || word.morph}</span>
                </div>
                {entry.data.derivation && (
                  <div className="original__fact">
                    <span className="original__fact-label">Root</span>
                    <span className="original__fact-value">{entry.data.derivation}</span>
                  </div>
                )}
              </div>

              <div className="stack stack--tight">
                <div className="section__head" style={{ border: 0, margin: 0 }}>
                  <span className="panel__eyebrow">
                    {entry.data.occurrences.toLocaleString()} occurrences
                  </span>
                  <button type="button" className="link" onClick={() => onStrongs(entry.data.id)}>
                    See all
                  </button>
                </div>
                <Histogram counts={entry.data.histogram} />
              </div>
            </div>
          )}
        </div>
      )}

      {words.some((w) => w.variant) && (
        <p className="original__variant-note">
          Dimmed words are carried by the Received Text — the King James's source — but not by
          the critical editions the other three follow.
        </p>
      )}
    </>
  )
}

export function InterlinearSheet({ verseRef, translation, onClose, onStrongs }) {
  return (
    <Sheet dark title="Original" onClose={onClose}>
      <div className="original">
        <OriginalPanel verseRef={verseRef} translation={translation} onStrongs={onStrongs} />
      </div>
    </Sheet>
  )
}

export function Histogram({ counts }) {
  if (!counts?.length) return null
  const max = Math.max(...counts, 1)
  return (
    <>
      <div className="histogram">
        {counts.map((n, i) => (
          <div
            key={i}
            className={`histogram__bar${n === max ? ' histogram__bar--peak' : ''}`}
            style={{ height: `${Math.max(6, (n / max) * 100)}%` }}
          />
        ))}
      </div>
      <div className="histogram__labels">
        <span>Genesis</span>
        <span>Gospels</span>
        <span>Revelation</span>
      </div>
    </>
  )
}

/** A Strong's entry, and every verse the word stands in. */
export function StrongsSheet({ number, translation, onClose, onRead, onBack, backLabel }) {
  const entry = useAsync(() => api.strongs(number), [number])
  const [pages, setPages] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const first = useAsync(
    () => api.strongsVerses(number, { translation, limit: 25 }),
    [number, translation],
  )
  useEffect(() => setPages([]), [number, translation])

  const showing = `${number}/${translation}`
  const current = useRef(showing)
  current.current = showing

  const refs = [...(first.data?.refs ?? []), ...pages]
  const total = first.data?.total ?? 0
  const more = refs.length < total

  const loadMore = async () => {
    const asked = showing
    setBusy(true)
    setError(null)
    try {
      const next = await api.strongsVerses(number, { translation, limit: 25, offset: refs.length })
      if (current.current === asked) setPages((rows) => [...rows, ...next.refs])
    } catch (e) {
      if (current.current === asked) setError(e)
    } finally {
      if (current.current === asked) setBusy(false)
    }
  }

  const d = entry.data

  return (
    <Sheet eyebrow={d?.language} title={d?.lemma ?? number} onClose={onClose}>
      {onBack && (
        <button type="button" className="link" onClick={onBack}>
          ← Back to {backLabel}
        </button>
      )}

      {entry.loading && <Spinner label="Looking up" />}
      <ErrorNote error={entry.error} />

      {d && (
        <Panel>
          <div className="result__head">
            <Badge>{d.id}</Badge>
            {d.translit && <span className="tag">{d.translit}</span>}
            {d.pron && <span className="tag">{d.pron}</span>}
            <span className="tag" style={{ marginLeft: 'auto' }}>{d.occurrences.toLocaleString()}×</span>
          </div>
          {d.definition && <p className="result__text">{d.definition}</p>}
          {d.derivation && <p className="quote">{d.derivation}</p>}
          {d.kjv_usage && (
            <p className="quote">
              <span className="quote__label">KJV renders it</span> {d.kjv_usage}
            </p>
          )}
          {d.senses?.length > 0 && (
            <div className="senses">
              {d.senses.map((s) => (
                <span key={s.gloss} className="tag">{s.gloss} · {s.count}</span>
              ))}
            </div>
          )}
          {d.histogram && (
            <div className="stack stack--tight" style={{ marginTop: '0.9rem' }}>
              <Histogram counts={d.histogram} />
            </div>
          )}
        </Panel>
      )}

      {first.loading && <Spinner label="Gathering" />}
      <ErrorNote error={first.error} />

      {first.data && (
        <>
          <div className="section__head">
            <span className="section__title">Every occurrence</span>
            <span className="tag">{total.toLocaleString()} {total === 1 ? 'verse' : 'verses'} · {first.data.translation}</span>
          </div>
          <div className="results">
            {refs.map((ref) => (
              <article key={ref.ref} className="result">
                <div className="result__head">
                  <button
                    type="button"
                    className="result__ref"
                    style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                    onClick={() => onRead(ref.book, ref.chapter, ref.verse)}
                  >
                    {ref.label}
                  </button>
                  {ref.hits > 1 && <span className="tag">{ref.hits}×</span>}
                </div>
                {ref.text && <p className="result__text">{ref.text}</p>}
                <p className="quote">{ref.glosses}</p>
              </article>
            ))}
          </div>
          <ErrorNote error={error} />
          {more && (
            <button type="button" className="btn" onClick={loadMore} disabled={busy}>
              {busy ? 'Loading…' : `Load more (${total - refs.length} left)`}
            </button>
          )}
        </>
      )}
    </Sheet>
  )
}

/** Related verses, by way of the Nave's topics a verse is filed under -- the
 * body shared by the mobile Cross-references sheet and the desktop rail's
 * Compare tab. */
export function ComparePanel({ verseRef, translation, onRead, onTopic }) {
  const { data, error, loading } = useAsync(() => api.crossRefs(verseRef, translation), [verseRef, translation])

  return (
    <>
      {loading && <Spinner label="Gathering" />}
      <ErrorNote error={error} />
      {data?.topics?.length === 0 && <p className="muted">Nave's does not file this verse under any topic.</p>}
      <div className="stack">
        {data?.topics?.map((group) => (
          <div key={group.topic_id}>
            <div className="section__head">
              <button type="button" className="link" onClick={() => onTopic(group.topic_id)}>
                {group.topic}
              </button>
              <span className="tag">{group.ref_count} refs</span>
            </div>
            <div className="results">
              {group.refs.map((ref) => (
                <article key={ref.ref} className="result">
                  <div className="result__head">
                    <button
                      type="button"
                      className="result__ref"
                      style={{ background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
                      onClick={() => onRead(ref.book, ref.chapter, ref.verse_start)}
                    >
                      {ref.ref}
                    </button>
                    <span className="result__kind">{data.translation}</span>
                  </div>
                  <p className="result__text">{ref.text}</p>
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

export function CrossRefSheet({ verseRef, translation, onClose, onRead, onTopic }) {
  const heading = useAsync(() => api.verse(verseRef, translation), [verseRef, translation])
  return (
    <Sheet
      eyebrow={`${verseRef} · ${heading.data?.label ?? verseRef}`}
      title="Cross-references"
      onClose={onClose}
    >
      <ComparePanel verseRef={verseRef} translation={translation} onRead={onRead} onTopic={onTopic} />
    </Sheet>
  )
}
