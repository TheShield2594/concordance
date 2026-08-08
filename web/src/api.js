const BASE = '/api'

async function request(path, options) {
  const res = await fetch(BASE + path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

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

  topic: (id, translation) => request(`/topics/${id}?${qs({ translation })}`),

  chapter: (book, chapter, translation) =>
    request(`/chapter/${book}/${chapter}?${qs({ translation })}`),

  verse: (ref, translation) => request(`/verse/${ref}?${qs({ translation })}`),

  crossRefs: (ref, translation) =>
    request(`/cross-refs/${ref}?${qs({ translation })}`),

  notes: ({ q = '', ref = '' } = {}) => request(`/notes?${qs({ q, ref })}`),

  createNote: (note) =>
    request('/notes', { method: 'POST', body: JSON.stringify(note) }),

  updateNote: (id, body) =>
    request(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) }),

  deleteNote: (id) => request(`/notes/${id}`, { method: 'DELETE' }),
}
