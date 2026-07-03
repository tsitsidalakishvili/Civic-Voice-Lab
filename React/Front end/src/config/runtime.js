const DEFAULT_API_BASE_URL = 'http://localhost:8000'
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

function pointsToLoopback(url) {
  const s = normalizeString(url)
  if (!s) return false
  try {
    const u = new URL(s)
    return u.hostname === 'localhost' || u.hostname === '127.0.0.1' || u.hostname === '[::1]'
  } catch {
    return /localhost|127\.0\.0\.1/.test(s)
  }
}

function pageIsServedFromLoopback() {
  if (typeof window === 'undefined') return true
  const h = window.location.hostname
  return h === 'localhost' || h === '127.0.0.1' || h === '[::1]'
}

/**
 * When the SPA is served from Vercel/HTTPS, `public/runtime-config.js` must not force
 * http://localhost:8010 (that breaks fetch with "Failed to fetch"). Prefer Vite
 * `VITE_API_BASE_URL` from the build; use runtime override only when it is non-loopback
 * or the page itself is on localhost.
 */
function resolveApiBaseUrl(overrides) {
  const fromVite = normalizeString(import.meta.env.VITE_API_BASE_URL)
  const fromRuntime = normalizeString(overrides.API_BASE_URL)
  let base = fromVite || fromRuntime || DEFAULT_API_BASE_URL
  if (typeof window !== 'undefined' && !pageIsServedFromLoopback() && pointsToLoopback(base)) {
    base = fromVite || DEFAULT_API_BASE_URL
    if (pointsToLoopback(base) && import.meta.env.PROD) {
      console.warn(
        '[Civic Voice Lab] API base URL points to localhost while the app is on a public host. ' +
          'Set VITE_API_BASE_URL in your host (e.g. Vercel → Environment Variables) to your API ' +
          '(e.g. https://your-api.onrender.com), or set window.__FS_RUNTIME_CONFIG__.API_BASE_URL before the app loads.',
      )
    }
  }
  return base
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
    apiBaseUrl: resolveApiBaseUrl(overrides),
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
