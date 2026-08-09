import { getRuntimeConfig } from '../config/runtime'

function apiBase() {
  return getRuntimeConfig().apiBaseUrl.replace(/\/$/, '')
}

export function safeReturnPath(value, fallback = '/') {
  const candidate = String(value || '').trim()
  if (!candidate.startsWith('/') || candidate.startsWith('//') || candidate.includes('\\')) return fallback
  if ([...candidate].some((character) => character.charCodeAt(0) < 32)) return fallback
  try {
    const parsed = new URL(candidate, 'https://fs.invalid')
    return parsed.origin === 'https://fs.invalid'
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : fallback
  } catch {
    return fallback
  }
}

/**
 * The backend decides which sign-in methods exist (FS_AUTH_MODE). The gate must
 * render what the server advertises, otherwise a password form is shown against
 * an OIDC-only backend and every attempt fails as an unexplained 401.
 */
export async function fetchAuthCapabilities() {
  const response = await fetch(`${apiBase()}/platform/auth/status`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    const error = new Error('The sign-in service could not be reached.')
    error.status = response.status
    throw error
  }
  const payload = await response.json()
  return {
    enabled: payload?.enabled !== false,
    mode: String(payload?.mode || ''),
    configured: payload?.configured === true,
    passwordLogin: payload?.passwordLogin === true,
    organizationLogin: payload?.organizationLogin === true,
  }
}

export function organizationLoginUrl(returnTo = '/', provider = getRuntimeConfig().oidcProvider) {
  const params = new URLSearchParams({ provider, returnTo: safeReturnPath(returnTo) })
  return `${apiBase()}/auth/login?${params.toString()}`
}

export async function loginWithCredentials(username, password) {
  const response = await fetch(`${apiBase()}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) {
    // 401 stays deliberately generic so it never reveals whether the username exists.
    const message = response.status === 429
      ? 'Too many attempts. Wait before trying again.'
      : response.status === 401
        ? 'The email or password is incorrect.'
        : response.status === 503
          ? 'Password sign-in is not enabled on this server.'
          : 'Sign-in failed because the service is unavailable.'
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return response.json()
}
