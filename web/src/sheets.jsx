import { useRef, useState } from 'react'

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
                    <CallNumber onClick={() => onRead(ref.book, ref.chapter)}>
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
