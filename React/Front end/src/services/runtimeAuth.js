import { getRuntimeConfig } from '../config/runtime'

const TOKEN_STORAGE_KEY = 'fs_auth_token'
const API_KEY_STORAGE_KEY = 'fs_auth_api_key'

function readStoredValue(key) {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(key) || '').trim()
}

export function getAuthSnapshot() {
  const runtime = getRuntimeConfig()
  return {
    enabled: runtime.authEnabled,
    mode: runtime.authMode === 'api_key' ? 'api_key' : 'bearer',
    headerName: runtime.authHeaderName,
    token: readStoredValue(TOKEN_STORAGE_KEY) || runtime.authToken,
    apiKey: readStoredValue(API_KEY_STORAGE_KEY) || runtime.authApiKey,
  }
}

export function getAuthHeaders() {
  const auth = getAuthSnapshot()
  if (!auth.enabled) return {}
  if (auth.mode === 'api_key') {
    if (!auth.apiKey) return {}
    return { [auth.headerName]: auth.apiKey }
  }
  if (!auth.token) return {}
  return { Authorization: `Bearer ${auth.token}` }
}

export function saveAuthCredentials({ token = '', apiKey = '' } = {}) {
  if (typeof window === 'undefined') return
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token.trim())
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  if (apiKey) window.localStorage.setItem(API_KEY_STORAGE_KEY, apiKey.trim())
  else window.localStorage.removeItem(API_KEY_STORAGE_KEY)
}

export function clearAuthCredentials() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  window.localStorage.removeItem(API_KEY_STORAGE_KEY)
}
