import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { renderWithProviders } from '../../test/render.jsx'
import { PlatformAccessGate } from '../PlatformAccessGate.jsx'

const status = (overrides) => ({
  ok: true,
  json: async () => ({
    contractVersion: 'fs-compliance.v1',
    enabled: true,
    configured: true,
    passwordLogin: false,
    organizationLogin: false,
    ...overrides,
  }),
})

describe('PlatformAccessGate sign-in methods', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the password form when the backend advertises password login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(status({ mode: 'password', passwordLogin: true })))
    renderWithProviders(<PlatformAccessGate />)
    expect(await screen.findByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /organization account/i })).not.toBeInTheDocument()
  })

  it('shows an organization sign-in link when the backend runs OIDC', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(status({ mode: 'oidc', organizationLogin: true })))
    renderWithProviders(<PlatformAccessGate />)
    const link = await screen.findByRole('link', { name: /organization account/i })
    expect(link.getAttribute('href')).toContain('/auth/login?provider=google')
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
  })

  it('explains the misconfiguration when no method is available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(status({ mode: 'oidc', configured: false })))
    renderWithProviders(<PlatformAccessGate />)
    expect(await screen.findByText(/no sign-in method configured/i)).toBeInTheDocument()
  })

  it('reports an unreachable sign-in service instead of a credential error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    renderWithProviders(<PlatformAccessGate />)
    await waitFor(() =>
      expect(screen.getByText(/sign-in service could not be reached/i)).toBeInTheDocument(),
    )
  })
})
