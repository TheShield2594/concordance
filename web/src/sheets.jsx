import { useEffect, useRef, useState } from 'react'

import { api } from './api.js'
import { CallNumber, ErrorNote, Sheet, Spinner } from './components.jsx'
import { formatDateTime } from './format.js'
import { useAsync } from './hooks.js'

/** Attach or edit notes on a verse. */
export function NoteSheet({ verseRef, translation, onClose, onChanged, onRead }) {
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
      // Saving empties the draft, which disables the button focus was sitting
      // on. Put the cursor back in the editor instead of dropping it on <body>.
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
    <Sheet
      title={verse.data?.label ?? 'Note'}
      subtitle={`${verseRef} · ${translation}`}
      onClose={onClose}
    >
      {text && <p className="quote">{text}</p>}
      <ErrorNote error={verse.error} />
      <ErrorNote error={notes.error} />

      <textarea
        ref={editor}
        value={editing ? editing.body : draft}
        onChange={(e) =>
          editing
            ? setEditing({ ...editing, body: e.target.value })
            : setDraft(e.target.value)
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

      {notes.loading && <Spinner label="Reading notes" />}

      {!notes.loading && existing.length > 0 && (
        <div className="stack">
          {existing.map((note) => (
            <article key={note.id} className="card card--verdigris">
              <div className="card__head">
                <CallNumber>{note.verse_ref}</CallNumber>
                <span className="tag" style={{ marginLeft: 'auto' }}>
                  {formatDateTime(note.updated_at)}
                </span>
              </div>
              <p className="note-body">{note.body}</p>
              <div className="card__actions">
                <button
                  type="button"
                  className="action"
                  onClick={() => setEditing({ id: note.id, body: note.body })}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="action"
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
    </Sheet>
  )
}

/**
 * The verse word by word in Hebrew, Aramaic or Greek.
 *
 * The words are not aligned to the English -- no public dataset lines up these
 * translations word for word -- so this sets the whole verse beside its
 * original rather than pretending to point at one word from the other side.
 */
export function InterlinearSheet({ verseRef, translation, onClose, onStrongs }) {
  const { data, error, loading } = useAsync(
    () => api.interlinear(verseRef, translation),
    [verseRef, translation],
  )
  const words = data?.words ?? []

  return (
    <Sheet
      title={data?.label ?? 'Original'}
      subtitle={`${verseRef}${data?.language ? ` · ${data.language}` : ''}`}
      onClose={onClose}
    >
      {loading && <Spinner label="Opening" />}
      <ErrorNote error={error} />

      {data?.verse && <p className="quote">{data.verse.text}</p>}

      {data && words.length === 0 && (
        <p className="muted">
          No tagged original for this verse. The Hebrew and Greek follow the
          versification of English Bibles, and a few verses divide differently.
        </p>
      )}

      {words.length > 0 && (
        <div className="interlinear" dir={data.direction}>
          {words.map((word) => (
            <button
              key={`${word.verse}-${word.seq}`}
              type="button"
              // The grid runs right to left for Hebrew, but the slip's own
              // contents are English and read the other way. Without this the
              // bidi algorithm drags their punctuation across: "and <obj.>"
              // comes out "<.and <obj".
              dir="ltr"
              className={`slip${word.variant ? ' slip--variant' : ''}`}
              onClick={() => word.in_dictionary && onStrongs(word.strongs_base)}
              disabled={!word.in_dictionary}
              title={
                word.in_dictionary
                  ? `Strong's ${word.strongs_base}`
                  : 'A prefix or suffix; Strong’s never numbered these'
              }
            >
              <span
                className={`slip__word slip__word--${word.lang}`}
                dir={data.direction}
              >
                {word.surface}
              </span>
              <span className="slip__translit">{word.translit}</span>
              <span className="slip__gloss">{word.gloss}</span>
              <span className="slip__foot">
                {word.in_dictionary && (
                  <span className="callno callno--sm">{word.strongs_base}</span>
                )}
                <span className="slip__parsing">{word.parsing || word.morph}</span>
              </span>
            </button>
          ))}
        </div>
      )}

      {words.some((w) => w.variant) && (
        <p className="muted muted--foot">
          Dimmed words are carried by the Received Text — the King James's
          source — but not by the critical editions the other three follow.
        </p>
      )}
    </Sheet>
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
  // A fresh word starts the list over; without this the previous word's
  // occurrences stay stacked underneath the new one's.
  useEffect(() => setPages([]), [number, translation])

  // Which word the list currently belongs to. A "load more" already in flight
  // when the reader taps through to another word must not land its page --
  // or its error -- on top of the new one's occurrences.
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
      const next = await api.strongsVerses(number, {
        translation,
        limit: 25,
        offset: refs.length,
      })
      if (current.current === asked) setPages((rows) => [...rows, ...next.refs])
    } catch (e) {
      if (current.current === asked) setError(e)
    } finally {
      if (current.current === asked) setBusy(false)
    }
  }

  const d = entry.data

  return (
    <Sheet
      title={d?.lemma ? `${d.lemma}` : number}
      subtitle={`${number}${d?.language ? ` · ${d.language}` : ''}`}
      onClose={onClose}
    >
      {onBack && (
        <button type="button" className="link" onClick={onBack}>
          ← Back to {backLabel}
        </button>
      )}

      {entry.loading && <Spinner label="Looking up" />}
      <ErrorNote error={entry.error} />

      {d && (
        <article className="card card--verdigris">
          <div className="card__head">
            <CallNumber>{d.id}</CallNumber>
            {d.translit && <span className="tag">{d.translit}</span>}
            {d.pron && <span className="tag">{d.pron}</span>}
            <span className="tag" style={{ marginLeft: 'auto' }}>
              {d.occurrences.toLocaleString()}×
            </span>
          </div>
          <p className={`lemma lemma--${d.lang}`} dir={d.direction}>
            {d.lemma}
          </p>
          {d.definition && <p className="card__text">{d.definition}</p>}
          {d.derivation && <p className="quote">{d.derivation}</p>}
          {d.kjv_usage && (
            <p className="quote">
              <span className="quote__label">KJV renders it</span> {d.kjv_usage}
            </p>
          )}
          {d.senses?.length > 0 && (
            <div className="senses">
              {d.senses.map((s) => (
                <span key={s.gloss} className="tag tag--count">
                  {s.gloss} · {s.count}
                </span>
              ))}
            </div>
          )}
        </article>
      )}

      {first.loading && <Spinner label="Gathering" />}
      <ErrorNote error={first.error} />

      {first.data && (
        <>
          <div className="section__head">
            <span className="section__title">Every occurrence</span>
            <span className="tag tag--onink">
              {total.toLocaleString()} {total === 1 ? 'verse' : 'verses'} ·{' '}
              {first.data.translation}
            </span>
          </div>
          <div className="stack">
            {refs.map((ref) => (
              <article key={ref.ref} className="card">
                <div className="card__head">
                  <CallNumber onClick={() => onRead(ref.book, ref.chapter, ref.verse)}>
                    {ref.ref}
                  </CallNumber>
                  <span className="tag">{ref.label}</span>
                  {ref.hits > 1 && (
                    <span className="tag tag--count">{ref.hits}×</span>
                  )}
                </div>
                {ref.text && <p className="card__text">{ref.text}</p>}
                <p className="quote">{ref.glosses}</p>
              </article>
            ))}
          </div>
          <ErrorNote error={error} />
          {more && (
            <button
              type="button"
              className="btn"
              onClick={loadMore}
              disabled={busy}
            >
              {busy ? 'Loading…' : `Load more (${total - refs.length} left)`}
            </button>
          )}
        </>
      )}
    </Sheet>
  )
}

/** Related verses, by way of the Nave's topics a verse is filed under. */
export function CrossRefSheet({ verseRef, translation, onClose, onRead, onTopic }) {
  const { data, error, loading } = useAsync(
    () => api.crossRefs(verseRef, translation),
    [verseRef, translation],
  )
  const heading = useAsync(
    () => api.verse(verseRef, translation).then((v) => v.label),
    [verseRef, translation],
  )
  const label = heading.data ?? verseRef

  return (
    <Sheet title="Cross-references" subtitle={`${verseRef} · ${label}`} onClose={onClose}>
      {loading && <Spinner label="Gathering" />}
      <ErrorNote error={error} />
      {data?.topics?.length === 0 && (
        <p className="muted">Nave's does not file this verse under any topic.</p>
      )}
      <div className="stack">
        {data?.topics?.map((group) => (
          <div key={group.topic_id}>
            <div className="section__head">
              <button
                type="button"
                className="link"
                onClick={() => onTopic(group.topic_id)}
              >
                {group.topic}
              </button>
              <span className="tag tag--onink">{group.ref_count} refs</span>
            </div>
            <div className="stack">
              {group.refs.map((ref) => (
                <article key={ref.ref} className="card card--verdigris">
                  <div className="card__head">
                    <CallNumber
                      onClick={() => onRead(ref.book, ref.chapter, ref.verse_start)}
                    >
                      {ref.ref}
                    </CallNumber>
                    <span className="tag">{data.translation}</span>
                  </div>
                  <p className="card__text">{ref.text}</p>
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Sheet>
  )
}
