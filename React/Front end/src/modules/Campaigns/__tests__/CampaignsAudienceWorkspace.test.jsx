import React from 'react'
import { screen, fireEvent } from '@testing-library/react'

import { renderWithProviders } from '../../../test/render.jsx'
import { CampaignsAudienceWorkspace } from '../CampaignsAudienceWorkspace.jsx'

describe('CampaignsAudienceWorkspace', () => {
  it('renders the match view with the config rail', () => {
    renderWithProviders(<CampaignsAudienceWorkspace t={(key) => key} />)
    expect(screen.getByText('Find creators for your brand')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/remember\.ge/i)).toBeInTheDocument()
  })

  it('produces ranked matches and projections after analyzing a brand', () => {
    renderWithProviders(<CampaignsAudienceWorkspace t={(key) => key} />)
    fireEvent.change(screen.getByPlaceholderText(/remember\.ge/i), {
      target: { value: 'Remember' },
    })
    fireEvent.click(screen.getByRole('button', { name: /analyze & match/i }))
    expect(screen.getByText('Best-matched creators')).toBeInTheDocument()
    expect(screen.getByText('Estimated reach')).toBeInTheDocument()
  })

  it('shows the roster table when the roster tab is active', () => {
    renderWithProviders(
      <CampaignsAudienceWorkspace t={(key) => key} activeTabOverride="roster" />,
    )
    expect(screen.getByText('Creator roster')).toBeInTheDocument()
    expect(screen.getByText('Roster pulse')).toBeInTheDocument()
  })
})
