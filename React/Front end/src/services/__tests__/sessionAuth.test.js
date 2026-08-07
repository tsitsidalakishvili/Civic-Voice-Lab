import { describe, expect, it } from 'vitest'
import { safeReturnPath } from '../sessionAuth'

describe('safeReturnPath', () => {
  it('keeps same-app paths and query strings', () => {
    expect(safeReturnPath('/due-diligence?case=1')).toBe('/due-diligence?case=1')
  })

  it.each(['https://evil.test', '//evil.test', '/\\evil.test', 'javascript:alert(1)'])(
    'rejects unsafe return path %s',
    (value) => expect(safeReturnPath(value)).toBe('/'),
  )
})
