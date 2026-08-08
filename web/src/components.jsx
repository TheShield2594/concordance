import { useEffect, useRef } from 'react'

/** The call number: a reference as a stamped catalogue mark. PHP.4.6 */
export function CallNumber({ children, onInk, large, onClick, title }) {
  const className = [
    'callno',
    onInk && 'callno--onink',
    large && 'callno--lg',
    onClick && 'callno--button',
  ]
    .filter(Boolean)
    .join(' ')
  if (!onClick) return <span className={className}>{children}</span>
  return (
    <button type="button" className={className} onClick={onClick} title={title}>
      {children}
    </button>
  )
}

export function SearchField({ value, onChange, placeholder, autoFocus }) {
  const ref = useRef(null)
  useEffect(() => {
    if (autoFocus) ref.current?.focus()
  }, [autoFocus])
  return (
    <div className="field">
      <span className="field__glyph" aria-hidden="true">
        ⌕
      </span>
      <input
        ref={ref}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        type="search"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck="false"
        aria-label={placeholder}
      />
      {value && (
        <button
          type="button"
          className="field__clear"
          onClick={() => onChange('')}
          aria-label="Clear search"
        >
          ✕
        </button>
      )}
    </div>
  )
}

export function Chips({ options, value, onChange, label }) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className="chip"
          aria-pressed={value === option}
          onClick={() => onChange(option)}
        >
          {option === 'ALL' ? 'All' : option}
        </button>
      ))}
    </div>
  )
}

export function Section({ title, aside, children }) {
  return (
    <section>
      <div className="section__head">
        <span className="section__title">{title}</span>
        {aside && <span className="tag tag--onink">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

export function Empty({ mark, children }) {
  return (
    <div className="empty">
      <span className="empty__mark">{mark}</span>
      {children}
    </div>
  )
}

export function Spinner({ label = 'Searching' }) {
  return <div className="spinner">{label}…</div>
}

export function ErrorNote({ error }) {
  if (!error) return null
  return (
    <Empty mark="Error">
      <p>{error.message}</p>
    </Empty>
  )
}

/** Verse text with FTS hits wrapped in <mark>. */
export function Marked({ segments, text }) {
  if (!segments) return <>{text}</>
  return (
    <>
      {segments.map((seg, i) =>
        seg.hit ? <mark key={i}>{seg.text}</mark> : <span key={i}>{seg.text}</span>,
      )}
    </>
  )
}

/**
 * A search result. Reference stamp, translation tag, verse text with the
 * matched terms marked, and the three actions.
 */
export function VerseCard({ verse, onRead, onNote, onCrossRefs, noteCount }) {
  return (
    <article className="card">
      <div className="card__head">
        <CallNumber>{verse.ref}</CallNumber>
        <span className="tag">{verse.translation}</span>
        <span className="tag" style={{ marginLeft: 'auto' }}>
          {verse.book_name} {verse.chapter}:{verse.verse}
        </span>
      </div>
      <p className="card__text">
        <Marked segments={verse.segments} text={verse.text} />
      </p>
      <div className="card__actions">
        <button type="button" className="action" onClick={() => onRead(verse)}>
          Read chapter
        </button>
        <button
          type="button"
          className="action action--verdigris"
          onClick={() => onNote(verse)}
        >
          {noteCount ? `Notes (${noteCount})` : 'Add note'}
        </button>
        <button
          type="button"
          className="action action--verdigris"
          onClick={() => onCrossRefs(verse)}
        >
          Cross-refs
        </button>
      </div>
    </article>
  )
}

export function TopicRow({ topic, onOpen }) {
  return (
    <button type="button" className="row" onClick={() => onOpen(topic)}>
      <span className="row__name">{topic.name}</span>
      <span className="tag tag--count">
        {topic.ref_count} {topic.ref_count === 1 ? 'ref' : 'refs'}
      </span>
    </button>
  )
}

/** Bottom sheet used for the note editor and cross-references. */
export function Sheet({ title, subtitle, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div
      className="sheet-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="sheet">
        <div className="sheet__head">
          <div>
            <h2 className="sheet__title">{title}</h2>
            {subtitle && <div className="tag tag--onink">{subtitle}</div>}
          </div>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
