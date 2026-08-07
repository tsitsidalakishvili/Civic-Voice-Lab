import { describe, expect, it } from 'vitest'
import { buildLoginUrl, safeReturnPath } from '../sessionAuth'
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

describe('Google Workspace login', () => {
  it('always sends the Google provider and a safe relative returnTo', () => {
    const login = new URL(buildLoginUrl('/due-diligence?case=synthetic'))
    expect(login.pathname).toBe('/auth/login')
    expect(login.searchParams.get('provider')).toBe('google')
    expect(login.searchParams.get('returnTo')).toBe('/due-diligence?case=synthetic')
  })

  it('does not forward an external return target', () => {
    const login = new URL(buildLoginUrl('https://example.invalid/escape'))
    expect(login.searchParams.get('returnTo')).toBe('/')
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
