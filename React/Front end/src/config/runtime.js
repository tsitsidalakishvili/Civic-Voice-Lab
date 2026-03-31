const DEFAULT_API_BASE_URL = 'http://localhost:8010'
const TRUTHY_VALUES = new Set(['1', 'true', 'yes', 'on'])

function readRuntimeOverrides() {
  if (typeof window === 'undefined') return {}
  const value = window.__FS_RUNTIME_CONFIG__
  return value && typeof value === 'object' ? value : {}
}

function normalizeString(value) {
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' ? value.trim() : ''
}

function readValue(envValue, runtimeValue, fallback = '') {
  return normalizeString(envValue) || normalizeString(runtimeValue) || fallback
}

function readBool(envValue, runtimeValue, fallback = false) {
  const raw = readValue(envValue, runtimeValue, '')
  if (!raw) return fallback
  return TRUTHY_VALUES.has(raw.toLowerCase())
}

export function getRuntimeConfig() {
  const overrides = readRuntimeOverrides()
  return {
    apiBaseUrl: readValue(
      import.meta.env.VITE_API_BASE_URL,
      overrides.API_BASE_URL,
      DEFAULT_API_BASE_URL,
    ),
    authEnabled: readBool(
      import.meta.env.VITE_AUTH_ENABLED,
      overrides.AUTH_ENABLED,
      false,
    ),
    authMode: readValue(
      import.meta.env.VITE_AUTH_MODE,
      overrides.AUTH_MODE,
      'bearer',
    ).toLowerCase(),
    authToken: readValue(
      import.meta.env.VITE_AUTH_TOKEN,
      overrides.AUTH_TOKEN,
      '',
    ),
    authApiKey: readValue(
      import.meta.env.VITE_AUTH_API_KEY,
      overrides.AUTH_API_KEY,
      '',
    ),
    authHeaderName: readValue(
      import.meta.env.VITE_AUTH_HEADER_NAME,
      overrides.AUTH_HEADER_NAME,
      'X-FS-API-Key',
    ),
  }
}
