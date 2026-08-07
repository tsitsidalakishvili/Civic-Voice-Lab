import { afterEach, describe, expect, it, vi } from 'vitest'
import { loginWithCredentials, safeReturnPath } from '../sessionAuth'
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
      'The username or password is incorrect.',
    )
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
