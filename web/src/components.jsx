import { useEffect, useRef } from 'react'

import { IconClose, IconMoon, IconSearch, IconSun } from './icons.jsx'

/** A dark badge, light type -- Strong's numbers, occurrence counts. */
export function Badge({ children, tone, onClick, title }) {
  const className = ['badge', tone && `badge--${tone}`, onClick && 'badge--button']
    .filter(Boolean)
    .join(' ')
  if (!onClick) return <span className={className}>{children}</span>
  return (
    <button type="button" className={className} onClick={onClick} title={title}>
      {children}
    </button>
  )
}

/**
 * A reference, stamped. Dark badge, light monospace, the same shape in every
 * theme -- the app's signature element, and the one piece of chrome that never
 * varies. Use it where a reference names what is on screen; a reference inside
 * a flowing list stays quiet.
 *
 * `aside` is the second rank inside the same stamp -- a translation code, or
 * the human label beside a call number -- set behind a hairline.
 */
export function Reference({ children, aside, onClick, title, className }) {
  const cls = ['ref-stamp', className].filter(Boolean).join(' ')
  const inner = (
    <>
      <span>{children}</span>
      {aside && <span className="ref-stamp__aside">{aside}</span>}
    </>
  )
  if (!onClick) return <span className={cls}>{inner}</span>
  return (
    <button type="button" className={cls} onClick={onClick} title={title}>
      {inner}
    </button>
  )
}

/* Day and Night are choices; Auto is the absence of one, so it sits between
   them rather than at an end. */
const READING_MODES = [
  { id: 'day', label: 'Day', Icon: IconSun },
  { id: 'auto', label: 'Auto' },
  { id: 'night', label: 'Night', Icon: IconMoon },
]

/** Which palette the reading surface uses: follow the system, or don't. */
export function ReadingModeSwitch({ value, onChange }) {
  return (
    <div className="mode-switch" role="group" aria-label="Reading mode">
      {READING_MODES.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          className="mode-switch__btn"
          aria-pressed={value === id}
          aria-label={`${label} reading`}
          title={`${label} reading`}
          onClick={() => onChange(id)}
        >
          {Icon ? <Icon /> : 'A'}
        </button>
      ))}
    </div>
  )
}

export function SearchField({ value, onChange, placeholder, autoFocus }) {
  const ref = useRef(null)
  useEffect(() => {
    if (autoFocus) ref.current?.focus()
  }, [autoFocus])
  return (
    <div className="field">
      <span className="field__icon">
        <IconSearch size={17} />
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
          <IconClose size={13} />
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

/** The bordered / filled / dark container the whole app builds panels from. */
export function Panel({ variant, flush, className, children, as: As = 'div', ...rest }) {
  const cls = ['panel', variant && `panel--${variant}`, flush && 'panel--flush', className]
    .filter(Boolean)
    .join(' ')
  return (
    <As className={cls} {...rest}>
      {children}
    </As>
  )
}

export function Section({ title, aside, children }) {
  return (
    <section className="section">
      <div className="section__head">
        <span className="section__title">{title}</span>
        {aside !== undefined && <span className="section__aside">{aside}</span>}
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
    <Empty mark="Something went wrong">
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

const MATCH_LABEL = { exact: 'Exact', meaning: 'Related' }

/**
 * A search result: reference, how it matched, verse text, and the actions
 * that follow it -- a flowing row with a hairline beneath it, not a boxed
 * card. Scripture carries the weight; the chrome around it stays quiet.
 */
export function ResultRow({ verse, onRead, onNote, onCrossRefs, onOriginal, noteCount }) {
  return (
    <article className="result">
      <div className="result__head">
        <span className="result__ref">{verse.book_name} {verse.chapter}:{verse.verse}</span>
        <span className="result__kind">
          {/* Several translations can appear in one ALL-translations list, so
              the kind tag never replaces the translation code -- it just
              rides alongside it. */}
          {verse.match_kind && MATCH_LABEL[verse.match_kind]
            ? `${MATCH_LABEL[verse.match_kind]} · ${verse.translation}`
            : verse.translation}
        </span>
      </div>
      <p className="result__text">
        <Marked segments={verse.segments} text={verse.text} />
      </p>
      <div className="result__actions">
        <button type="button" className="result__action" onClick={() => onRead(verse)}>
          Read chapter
        </button>
        <button type="button" className="result__action" onClick={() => onNote(verse)}>
          {noteCount ? `Notes (${noteCount})` : 'Add note'}
        </button>
        <button type="button" className="result__action" onClick={() => onCrossRefs(verse)}>
          Cross-refs
        </button>
        {onOriginal && (
          <button type="button" className="result__action" onClick={() => onOriginal(verse)}>
            Original
          </button>
        )}
      </div>
    </article>
  )
}

export function TopicRow({ topic, onOpen }) {
  return (
    <button type="button" className="row" onClick={() => onOpen(topic)}>
      <span className="row__name">{topic.name}</span>
      <span className="tag">
        {topic.ref_count} {topic.ref_count === 1 ? 'ref' : 'refs'}
      </span>
    </button>
  )
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'

/** Bottom sheet: the note editor, cross-references, Strong's, and (in dark
 * dress) the Original sheet. */
export function Sheet({ title, eyebrow, onClose, dark, children }) {
  const panel = useRef(null)
  const close = useRef(onClose)
  close.current = onClose

  useEffect(() => {
    const opener = document.activeElement
    panel.current?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') {
        close.current()
        return
      }
      if (e.key !== 'Tab' || !panel.current) return
      const stops = [...panel.current.querySelectorAll(FOCUSABLE)].filter(
        (el) => el.offsetParent !== null,
      )
      if (!stops.length) return
      const first = stops[0]
      const last = stops[stops.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === panel.current)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [])

  return (
    <div
      className="sheet-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={`sheet${dark ? ' sheet--dark' : ''}`}
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="sheet__head">
          <div>
            {eyebrow && <p className="sheet__eyebrow">{eyebrow}</p>}
            <h2 className="sheet__title">{title}</h2>
          </div>
          <button type="button" className="sheet__close" onClick={onClose} aria-label="Close">
            <IconClose size={15} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
