export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function formatError(data, status) {
  if (data && typeof data.detail === 'string') return data.detail
  if (data && Array.isArray(data.detail)) {
    return data.detail
      .map((d) => {
        const where = (d.loc || []).filter((p) => p !== 'body' && p !== 'query').join('.')
        return where ? `${where}: ${d.msg}` : d.msg
      })
      .join('\n')
  }
  if (status === 502 || status === 504) return "L'API non risponde: controlla che il container 'api' sia avviato."
  return `Errore ${status}`
}

async function request(method, url, body) {
  const options = { method, headers: {} }
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  let response
  try {
    response = await fetch(`/api${url}`, options)
  } catch {
    throw new ApiError("Impossibile raggiungere l'API: controlla che il backend sia avviato.", 0)
  }
  if (response.status === 204) return null
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (response.status === 401 && !url.startsWith('/auth/')) {
    // Sessione scaduta: l'app torna alla pagina di login
    window.dispatchEvent(new Event('netmap:unauthorized'))
  }
  if (!response.ok) throw new ApiError(formatError(data, response.status), response.status)
  return data
}

export const api = {
  get: (url) => request('GET', url),
  post: (url, body) => request('POST', url, body),
  patch: (url, body) => request('PATCH', url, body),
  put: (url, body) => request('PUT', url, body),
  del: (url) => request('DELETE', url),
}

/** { a: 1, b: '', c: null } -> "?a=1" */
export function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.append(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
