import { useCallback, useEffect, useRef, useState } from 'react'

/** Hash routing, so a reload (or a shared Tailscale link) lands in the same place. */
export function parseHash(hash) {
  const raw = (hash || '').replace(/^#\/?/, '')
  const [path, search] = raw.split('?')
  const parts = path.split('/').filter(Boolean)
  return {
    tab: parts[0] || 'search',
    parts: parts.slice(1),
    query: Object.fromEntries(new URLSearchParams(search || '')),
  }
}

export function useRoute() {
  const [route, setRoute] = useState(() => parseHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const navigate = useCallback((to, { replace = false } = {}) => {
    const next = to.startsWith('#') ? to : `#/${to.replace(/^\//, '')}`
    if (window.location.hash === next) return
    if (replace) window.history.replaceState(null, '', next)
    else window.location.hash = next
    setRoute(parseHash(next))
  }, [])
  return [route, navigate]
}

/** Value that settles after the user stops typing. */
export function useDebounced(value, delay = 180) {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return settled
}

/**
 * Run an async function, keeping only the latest result. `deps` drives reruns;
 * returns { data, error, loading, reload }.
 */
export function useAsync(fn, deps, { skip = false } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: !skip })
  const [nonce, setNonce] = useState(0)
  const latest = useRef(0)

  useEffect(() => {
    if (skip) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const ticket = ++latest.current
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => {
        if (ticket === latest.current) setState({ data, error: null, loading: false })
      })
      .catch((error) => {
        if (ticket === latest.current) setState({ data: null, error, loading: false })
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, skip])

  return { ...state, reload: useCallback(() => setNonce((n) => n + 1), []) }
}

/** Remembered translation preference. */
export function useStoredState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      return window.localStorage.getItem(key) ?? initial
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(key, value)
    } catch {
      /* private mode -- preference just won't persist */
    }
  }, [key, value])
  return [value, setValue]
}
