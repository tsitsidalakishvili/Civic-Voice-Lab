import { getRuntimeConfig } from '../config/runtime'

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

export async function loginWithCredentials(username, password) {
  const runtime = getRuntimeConfig()
  const base = runtime.apiBaseUrl.replace(/\/$/, '')
  const response = await fetch(`${base}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) {
    const error = new Error(response.status === 429
      ? 'Too many attempts. Wait before trying again.'
      : 'The username or password is incorrect.')
    error.status = response.status
    throw error
  }
  return response.json()
}
