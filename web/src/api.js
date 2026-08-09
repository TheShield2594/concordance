const BASE = '/api'

/** FastAPI sends `detail` as a string, or as a list of objects for a 422. */
function describe(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail
      .map((d) => (typeof d === 'string' ? d : [d.loc?.join('.'), d.msg].filter(Boolean).join(': ')))
      .filter(Boolean)
      .join('; ')
  return detail.msg || JSON.stringify(detail)
}

async function request(path, options) {
  const res = await fetch(BASE + path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = describe((await res.json()).detail) || detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

/** Path segments get encoded so a stray `/` or `?` can't redraw the URL. */
const enc = (value) => encodeURIComponent(String(value))

const qs = (params) =>
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')

export const api = {
  meta: () => request('/meta'),

  search: ({ q, translation = 'ALL', limit = 25, offset = 0, include, sort }) =>
    request(`/search?${qs({ q, translation, limit, offset, include, sort })}`),

  topics: ({ q = '', limit = 60, offset = 0 } = {}) =>
    request(`/topics?${qs({ q, limit, offset })}`),

  topic: (id, translation) =>
    request(`/topics/${enc(id)}?${qs({ translation })}`),

  chapter: (book, chapter, translation) =>
    request(`/chapter/${enc(book)}/${enc(chapter)}?${qs({ translation })}`),

  verse: (ref, translation) => request(`/verse/${enc(ref)}?${qs({ translation })}`),

  crossRefs: (ref, translation) =>
    request(`/cross-refs/${enc(ref)}?${qs({ translation })}`),

  interlinear: (ref, translation) =>
    request(`/interlinear/${enc(ref)}?${qs({ translation })}`),

  strongs: (number) => request(`/strongs/${enc(number)}`),

  strongsVerses: (number, { translation, limit = 25, offset = 0 } = {}) =>
    request(`/strongs/${enc(number)}/verses?${qs({ translation, limit, offset })}`),

  notes: ({ q = '', ref = '' } = {}) => request(`/notes?${qs({ q, ref })}`),

  createNote: (note) =>
    request('/notes', { method: 'POST', body: JSON.stringify(note) }),

  updateNote: (id, body) =>
    request(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) }),

  deleteNote: (id) => request(`/notes/${id}`, { method: 'DELETE' }),
}
