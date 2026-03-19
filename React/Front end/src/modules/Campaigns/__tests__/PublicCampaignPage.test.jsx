import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { PublicCampaignPage } from '../PublicCampaignPage.jsx'

vi.mock('../../../services/api', () => ({
  getJson: vi.fn(),
  requestJson: vi.fn(),
}))

import { getJson } from '../../../services/api'

describe('PublicCampaignPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the public campaign list', async () => {
    getJson.mockResolvedValueOnce([
      {
        campaignId: '1',
        name: 'Fix the park',
        problemTitle: 'Broken playground equipment',
        fundingTargetAmount: 5000,
        fundsRaisedAmount: 1200,
        currency: 'GEL',
        status: 'Funding',
      },
    ])
    render(<PublicCampaignPage campaignId={null} />)

    expect(await screen.findByText('Problem-Solving Campaigns')).toBeInTheDocument()
    expect(await screen.findByText('Fix the park')).toBeInTheDocument()
  })

  it('renders the public campaign detail view', async () => {
    getJson.mockImplementation((url) => {
      if (url.endsWith('/crm/campaigns/123')) {
        return Promise.resolve({
          campaignId: '123',
          name: 'Clean the river',
          problemTitle: 'River cleanup',
          fundingTargetAmount: 10000,
          fundsRaisedAmount: 2500,
          currency: 'GEL',
          status: 'Funding',
        })
      }
      if (url.includes('/funding-summary')) {
        return Promise.resolve({
          fundingTargetAmount: 10000,
          fundsRaisedAmount: 2500,
          currency: 'GEL',
          contributorCount: 3,
        })
      }
      if (url.includes('/transparency')) {
        return Promise.resolve({
          amountSpent: 0,
          remainingBalance: 2500,
          proofCount: 0,
          expenseCount: 0,
        })
      }
      return Promise.resolve([])
    })

    render(<PublicCampaignPage campaignId="123" />)

    expect(await screen.findByText('Clean the river')).toBeInTheDocument()
    expect(await screen.findByText('Overview')).toBeInTheDocument()
  })
})
