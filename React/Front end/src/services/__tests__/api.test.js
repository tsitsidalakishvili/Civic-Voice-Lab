import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearApiSessionState,
  getJson,
  requestJson,
  setActiveProcessingPurposeModule,
  setSessionCsrfToken,
} from '../api'

describe('session API transport', () => {
  beforeEach(() => {
    clearApiSessionState()
    setActiveProcessingPurposeModule('')
    globalThis.fetch = vi.fn()
  })
  afterEach(() => vi.restoreAllMocks())

  it('includes cookie credentials without authorization tokens', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    await getJson('/auth/me', { cacheMs: 0 })
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/auth/me'), {
      credentials: 'include',
      headers: {},
    })
    expect(JSON.stringify(fetch.mock.calls)).not.toMatch(/authorization|bearer|api.?key/i)
  })

  it('attaches the approved purpose only to due-diligence requests', async () => {
    fetch
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await getJson('/due-diligence/cases', { cacheMs: 0 })
    await getJson('/auth/me', { cacheMs: 0 })

    expect(fetch.mock.calls[0][1].headers).toEqual({
      'X-FS-Purpose-Id': 'dd-investigation',
    })
    expect(fetch.mock.calls[1][1].headers).toEqual({})
  })

  it('supports an explicit approved purpose for cross-module requests', async () => {
    fetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await getJson('/crm/summary', { cacheMs: 0, purposeId: 'dd-investigation' })

    expect(fetch.mock.calls[0][1].headers).toEqual({
      'X-FS-Purpose-Id': 'dd-investigation',
    })
  })

  it.each([
    ['crm', '/crm/summary', 'crm-operations'],
    ['deliberation', '/crm/segments', 'survey-consensus'],
    ['campaigns', '/crm/campaigns', 'campaign-operations'],
    ['deliberation', '/exports/job-1', 'survey-consensus'],
    ['data-hub', '/data-chat/ask', 'data-exploration'],
    ['campaigns', '/audience-discovery/analysis/start', 'audience-research'],
  ])('maps %s requests to their approved purpose', async (moduleId, path, purposeId) => {
    setActiveProcessingPurposeModule(moduleId)
    fetch.mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await getJson(path, { cacheMs: 0 })

    expect(fetch.mock.calls[0][1].headers).toEqual({ 'X-FS-Purpose-Id': purposeId })
  })

  it('adds the session CSRF token to mutations', async () => {
    setSessionCsrfToken('synthetic-csrf')
    fetch.mockResolvedValue(new Response(null, { status: 204 }))
    await requestJson('/auth/logout', { method: 'POST' })
    expect(fetch.mock.calls[0][1]).toMatchObject({
      credentials: 'include',
      headers: expect.objectContaining({ 'X-FS-CSRF': 'synthetic-csrf' }),
    })
  })

  it('does not reuse cached data after session state is cleared', async () => {
    fetch
      .mockResolvedValueOnce(new Response(JSON.stringify({ value: 1 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ value: 2 }), { status: 200 }))
    expect((await getJson('/private')).value).toBe(1)
    clearApiSessionState()
    expect((await getJson('/private')).value).toBe(2)
  })
})
