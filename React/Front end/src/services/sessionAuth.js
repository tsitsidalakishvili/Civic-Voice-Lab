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

export function buildLoginUrl(returnTo) {
  const runtime = getRuntimeConfig()
  const base = runtime.apiBaseUrl.replace(/\/$/, '')
  const query = new URLSearchParams({ returnTo: safeReturnPath(returnTo) })
  if (runtime.oidcProvider) query.set('provider', runtime.oidcProvider)
  return `${base}/auth/login?${query}`
}

export function beginOrganizationLogin(returnTo) {
  const current = `${window.location.pathname}${window.location.search}`
  window.location.assign(buildLoginUrl(returnTo || current))
}

export function principalKey(principal) {
  return String(principal?.id || principal?.userId || principal?.sub || principal?.email || '')
}
