import { getRuntimeConfig } from '../config/runtime'

/** Resolve on each use so production never keeps a stale base from first module load. */
export function getApiBaseUrl() {
  return getRuntimeConfig().apiBaseUrl
}

const DEFAULT_GET_CACHE_MS = 5000
const getCache = new Map()
const inflightGetRequests = new Map()
const authListeners = new Set()
let cacheGeneration = 0
let csrfToken = ''

const DUE_DILIGENCE_PURPOSE_ID = 'dd-investigation'

function purposeHeaders(path) {
  const normalizedPath = `/${String(path || '').replace(/^\/+/, '')}`
  return (normalizedPath === '/due-diligence' || normalizedPath.startsWith('/due-diligence/'))
    ? { 'X-FS-Purpose-Id': DUE_DILIGENCE_PURPOSE_ID }
    : {}
}

function buildUrl(path) {
  const base = getApiBaseUrl()
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

function buildGetRequestKey(url) {
  return `GET:${cacheGeneration}:${url}`
}

function cloneJson(value) {
  if (value === null || value === undefined) return value
  // Keep caller mutations from mutating cached state.
  if (typeof structuredClone === 'function') return structuredClone(value)
  return JSON.parse(JSON.stringify(value))
}

export function clearApiSessionState() {
  cacheGeneration += 1
  getCache.clear()
  inflightGetRequests.clear()
  csrfToken = ''
}

function invalidateGetCache() {
  cacheGeneration += 1
  getCache.clear()
  inflightGetRequests.clear()
}

export function setSessionCsrfToken(value = '') { csrfToken = String(value || '') }
export function onApiAuthEvent(listener) {
  authListeners.add(listener)
  return () => authListeners.delete(listener)
}

export class ApiError extends Error {
  constructor(message, status, code = '', detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

async function parseError(response) {
  const text = await response.text()
  // Try to extract a readable message from JSON error responses (e.g. FastAPI {"detail": "..."})
  try {
    const json = JSON.parse(text)
    const code = json?.error?.code || json?.detail?.code || ''
    if (typeof json?.detail === 'string') return new ApiError(json.detail, response.status, code, json)
    if (json?.detail && typeof json.detail === 'object') {
      return new ApiError(json.detail.message || 'Request failed.', response.status, code, json.detail)
    }
    if (typeof json?.message === 'string') return new ApiError(json.message, response.status, code, json)
    if (json?.error?.message) return new ApiError(json.error.message, response.status, code, json.error)
  } catch {
    // not JSON — fall through
  }
  return new ApiError(text || `Request failed: ${response.status}`, response.status)
}

async function requireOk(response) {
  if (response.ok) return response
  const error = await parseError(response)
  if (response.status === 401) {
    clearApiSessionState()
    authListeners.forEach((listener) => listener({ type: error.code === 'AUTH_SESSION_REVOKED' ? 'revoked' : 'unauthenticated', error }))
  } else if (response.status === 403 && error.code === 'ACCESS_REVOKED') {
    authListeners.forEach((listener) => listener({ type: 'unauthorized', error }))
  }
  throw error
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
    credentials: 'include',
    headers: purposeHeaders(path),
  })
    .then(async (response) => {
      await requireOk(response)
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
    invalidateGetCache()
  }
  const response = await fetch(url, {
    method,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(csrfToken ? { 'X-FS-CSRF': csrfToken } : {}),
      ...purposeHeaders(path),
      ...(headers || {}),
    },
    body: payload === undefined ? null : JSON.stringify(payload),
  })
  await requireOk(response)
  if (response.status === 204) return null
  return response.json()
}

export async function downloadFile(path, fallbackFileName = 'download') {
  const url = buildUrl(path)
  const response = await fetch(url, {
    credentials: 'include',
    headers: purposeHeaders(path),
  })
  await requireOk(response)
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
    invalidateGetCache()
  }
  const response = await fetch(url, {
    method,
    credentials: 'include',
    headers: {
      ...(csrfToken ? { 'X-FS-CSRF': csrfToken } : {}),
      ...purposeHeaders(path),
    },
    body: formData,
  })
  await requireOk(response)
  if (response.status === 204) return null
  return response.json()
}
