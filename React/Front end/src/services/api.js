import { getRuntimeConfig } from '../config/runtime'
import { getAuthHeaders, getAuthSnapshot } from './runtimeAuth'

/** Resolve on each use so production never keeps a stale base from first module load. */
export function getApiBaseUrl() {
  return getRuntimeConfig().apiBaseUrl
}

const DEFAULT_GET_CACHE_MS = 5000
const getCache = new Map()
const inflightGetRequests = new Map()

function buildUrl(path) {
  const base = getApiBaseUrl()
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

function buildGetRequestKey(url) {
  const auth = getAuthSnapshot()
  if (!auth.enabled) return `GET:public:${url}`
  const credential = auth.mode === 'api_key' ? auth.apiKey : auth.token
  const authSuffix = credential ? credential.slice(-6) : 'anon'
  return `GET:${auth.mode}:${auth.headerName}:${authSuffix}:${url}`
}

function cloneJson(value) {
  if (value === null || value === undefined) return value
  // Keep caller mutations from mutating cached state.
  if (typeof structuredClone === 'function') return structuredClone(value)
  return JSON.parse(JSON.stringify(value))
}

function clearGetCache() {
  getCache.clear()
  inflightGetRequests.clear()
}

async function parseError(response) {
  const text = await response.text()
  // Try to extract a readable message from JSON error responses (e.g. FastAPI {"detail": "..."})
  try {
    const json = JSON.parse(text)
    if (typeof json?.detail === 'string') return json.detail
    if (typeof json?.message === 'string') return json.message
    if (typeof json?.error === 'string') return json.error
  } catch {
    // not JSON — fall through
  }
  return text || `Request failed: ${response.status}`
}

export async function getJson(path, { cacheMs = DEFAULT_GET_CACHE_MS, forceRefresh = false } = {}) {
  const url = buildUrl(path)
  const key = buildGetRequestKey(url)
  const now = Date.now()
  if (!forceRefresh) {
    const cached = getCache.get(key)
    if (cached && cached.expiresAt > now) {
      return cloneJson(cached.value)
    }
    const pending = inflightGetRequests.get(key)
    if (pending) {
      return pending.then((value) => cloneJson(value))
    }
  }

  const pendingRequest = fetch(url, {
    headers: getAuthHeaders(),
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await parseError(response))
      }
      return response.json()
    })
    .then((payload) => {
      if (cacheMs > 0) {
        getCache.set(key, {
          expiresAt: Date.now() + cacheMs,
          value: payload,
        })
      } else {
        getCache.delete(key)
      }
      return payload
    })
    .finally(() => {
      inflightGetRequests.delete(key)
    })
  inflightGetRequests.set(key, pendingRequest)
  return pendingRequest.then((value) => cloneJson(value))
}

export async function requestJson(path, { method = 'POST', payload, headers } = {}) {
  const url = buildUrl(path)
  if (String(method).toUpperCase() !== 'GET') {
    clearGetCache()
  }
  const response = await fetch(url, {
    method,
    headers: {
      ...getAuthHeaders(),
      'Content-Type': 'application/json',
      ...(headers || {}),
    },
    body: payload === undefined ? null : JSON.stringify(payload),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  if (response.status === 204) return null
  return response.json()
}

export async function downloadFile(path, fallbackFileName = 'download') {
  const url = buildUrl(path)
  const response = await fetch(url, {
    headers: getAuthHeaders(),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/i)
  const fileName = match ? match[1] : fallbackFileName
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
  return fileName
}

export async function requestForm(path, { method = 'POST', formData } = {}) {
  const url = buildUrl(path)
  if (String(method).toUpperCase() !== 'GET') {
    clearGetCache()
  }
  const response = await fetch(url, {
    method,
    headers: getAuthHeaders(),
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  if (response.status === 204) return null
  return response.json()
}
