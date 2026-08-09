import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchAuthCapabilities, loginWithCredentials, organizationLoginUrl, safeReturnPath } from '../sessionAuth'
import { validateProductionApiOrigin } from '../../config/runtime'

describe('safeReturnPath', () => {
  it('keeps same-app paths and query strings', () => {
    expect(safeReturnPath('/due-diligence?case=1')).toBe('/due-diligence?case=1')
  })

  it.each(['https://evil.test', '//evil.test', '/\\evil.test', 'javascript:alert(1)'])(
    'rejects unsafe return path %s',
    (value) => expect(safeReturnPath(value)).toBe('/'),
  )
})

describe('temporary staff login', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('posts credentials with browser-managed cookies', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ authenticated: true }) })
    vi.stubGlobal('fetch', fetchMock)
    await loginWithCredentials('temporary-user', 'strong-password')
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/login$/), expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ username: 'temporary-user', password: 'strong-password' }),
    }))
  })

  it('returns a generic error for rejected credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    await expect(loginWithCredentials('wrong-user', 'wrong-password')).rejects.toThrow(
      'The email or password is incorrect.',
    )
  })

  it('does not blame the credential when password sign-in is disabled', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(loginWithCredentials('user', 'password')).rejects.toThrow(
      'Password sign-in is not enabled on this server.',
    )
  })
})

describe('advertised sign-in methods', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads the public auth status endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ enabled: true, mode: 'oidc', configured: true, organizationLogin: true, passwordLogin: false }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchAuthCapabilities()).resolves.toMatchObject({
      mode: 'oidc',
      organizationLogin: true,
      passwordLogin: false,
    })
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/platform\/auth\/status$/),
      expect.objectContaining({ method: 'GET' }),
    )
  })

  it('builds an organization login URL with a safe return path', () => {
    expect(organizationLoginUrl('https://evil.test')).toContain('returnTo=%2F')
    expect(organizationLoginUrl('/crm')).toContain('returnTo=%2Fcrm')
  })
})

describe('production API origin', () => {
  it('accepts one exact HTTPS origin', () => {
    expect(validateProductionApiOrigin('https://api.example.invalid')).toBe('https://api.example.invalid')
  })

  it.each(['', 'http://api.example.invalid', 'https://api.example.invalid/path', 'http://localhost:8010'])(
    'fails closed for %s',
    (value) => expect(() => validateProductionApiOrigin(value)).toThrow('Production API origin is not configured.'),
  )
})
