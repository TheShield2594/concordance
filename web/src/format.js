/**
 * Timestamps come back from SQLite's `datetime('now')`: naive UTC, no zone.
 * Append the Z before parsing so they render in whatever timezone you're in
 * rather than being read as local time and drifting by your offset.
 */
const parse = (value) => {
  if (!value) return null
  const iso = value.includes('T') ? value : value.replace(' ', 'T')
  const date = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateAndTime = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatDate(value) {
  const date = parse(value)
  return date ? dateOnly.format(date) : ''
}

export function formatDateTime(value) {
  const date = parse(value)
  return date ? dateAndTime.format(date) : ''
}
