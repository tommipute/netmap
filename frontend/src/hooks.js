import { useCallback, useEffect, useState } from 'react'
import { api, qs } from './api'

// Cache delle liste usate nei menu a tendina (sedi, ruoli, VLAN...). Si svuota dopo ogni modifica.
const cache = new Map()
const listeners = new Set()

export function invalidate() {
  cache.clear()
  listeners.forEach((fn) => fn())
}

function cachedGet(url) {
  if (!cache.has(url)) {
    cache.set(
      url,
      api.get(url).catch((err) => {
        cache.delete(url)
        throw err
      }),
    )
  }
  return cache.get(url)
}

/** Carica un URL dell'API. url = null -> non carica niente. */
export function useApi(url) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(url) })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!url) {
      setState({ data: null, error: null, loading: false })
      return undefined
    }
    let alive = true
    setState((prev) => ({ ...prev, loading: true }))
    api
      .get(url)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }))
    return () => {
      alive = false
    }
  }, [url, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}

/** Elenco completo (max 1000) di una risorsa, per i menu a tendina. path = null -> lista vuota. */
export function useOptions(path, params = {}) {
  const url = path ? `/${path}${qs({ limit: 1000, ...params })}` : null
  const [items, setItems] = useState([])
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const fn = () => setVersion((v) => v + 1)
    listeners.add(fn)
    return () => {
      listeners.delete(fn)
    }
  }, [])

  useEffect(() => {
    if (!url) {
      setItems([])
      return undefined
    }
    let alive = true
    cachedGet(url)
      .then((data) => alive && setItems(data.items))
      .catch(() => alive && setItems([]))
    return () => {
      alive = false
    }
  }, [url, version])

  return items
}

export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** Numero di modifiche della scansione in attesa: si aggiorna ogni 30 s e dopo ogni invalidate(). */
export function usePendingCount() {
  const [count, setCount] = useState(0)
  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .get('/discovery-changes/count')
        .then((data) => alive && setCount(data.pending))
        .catch(() => {})
    load()
    const timer = setInterval(load, 30000)
    listeners.add(load)
    return () => {
      alive = false
      clearInterval(timer)
      listeners.delete(load)
    }
  }, [])
  return count
}
