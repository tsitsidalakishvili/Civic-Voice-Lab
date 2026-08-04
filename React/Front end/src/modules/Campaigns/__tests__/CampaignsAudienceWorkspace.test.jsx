import React from 'react'
import { screen, fireEvent } from '@testing-library/react'

import { renderWithProviders } from '../../../test/render.jsx'
import { CampaignsAudienceWorkspace } from '../CampaignsAudienceWorkspace.jsx'

describe('CampaignsAudienceWorkspace', () => {
  it('renders the match view with the config rail', () => {
    renderWithProviders(<CampaignsAudienceWorkspace t={(key) => key} />)
    expect(screen.getByText('Find messengers for your campaign')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/EU integration/i)).toBeInTheDocument()
  })

  it('produces ranked matches and projections after analyzing a campaign', () => {
    renderWithProviders(<CampaignsAudienceWorkspace t={(key) => key} />)
    fireEvent.change(screen.getByPlaceholderText(/EU integration/i), {
      target: { value: 'healthcare reform' },
    })
    fireEvent.click(screen.getByRole('button', { name: /analyze & match/i }))
    expect(screen.getByText('Best-matched messengers')).toBeInTheDocument()
    expect(screen.getByText('Estimated reach')).toBeInTheDocument()
  })

  it('shows the roster table when the roster tab is active', () => {
    renderWithProviders(
      <CampaignsAudienceWorkspace t={(key) => key} activeTabOverride="roster" />,
    )
    expect(screen.getByText('Messenger roster')).toBeInTheDocument()
    expect(screen.getByText('Roster pulse')).toBeInTheDocument()
  })
})
