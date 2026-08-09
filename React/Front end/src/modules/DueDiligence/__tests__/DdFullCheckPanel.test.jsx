import React from 'react'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import { requestJson } from '@/services/api'
import { renderWithProviders } from '../../../test/render.jsx'
import { DdFullCheckPanel } from '../DdFullCheckPanel.jsx'

vi.mock('@/services/api', () => ({
  requestJson: vi.fn(),
  getApiBaseUrl: () => 'http://localhost:8010',
}))

const source = (id, label, status, hitCount, detail, requiresConfiguration = false) => ({
  id,
  label,
  status,
  hitCount,
  detail,
  requiresConfiguration,
})

const fullCheckResponse = {
  caseId: 'case-1',
  subject: 'Test Subject',
  subjectType: 'Person',
  generatedAt: '2026-08-09T10:00:00+00:00',
  demo: false,
  sources: [
    source('wikidata', 'Wikidata', 'ok', 2, 'Matched 2 Wikidata entities.'),
    source('wikipedia', 'Wikipedia', 'ok', 1, 'Matched 1 Wikipedia article.'),
    source(
      'opensanctions',
      'OpenSanctions (sanctions & PEP screening)',
      'not-configured',
      0,
      'Not configured: set OPENSANCTIONS_API_KEY to enable this source.',
      true,
    ),
    source('news', 'International news (GDELT)', 'error', 0, 'GDELT returned HTTP 429.'),
    source(
      'declarations',
      'Georgian asset declarations',
      'no-data',
      0,
      'No asset declarations matched this subject.',
    ),
    source('georgian-media', 'Georgian media monitor', 'ok', 1, 'Found 1 local media mention.'),
    source(
      'company-registry',
      'Georgian company registry (Companyinfo.ge)',
      'blocked',
      0,
      'Blocked: no identification code recorded for this case.',
      true,
    ),
    source(
      'facebook',
      'Facebook public groups (Apify)',
      'not-configured',
      0,
      'Not configured: set APIFY_TOKEN to enable this source.',
      true,
    ),
  ],
  summary: {
    riskLevel: 'Low',
    riskScore: 12,
    totalHits: 4,
    sourcesChecked: 8,
    sourcesWithData: 3,
    sourcesRequiringConfiguration: 3,
  },
  results: {},
  aiReport: null,
  warnings: ['News search could not be completed on this run.'],
  reportId: '11111111-2222-3333-4444-555555555555',
  storedAt: '2026-08-09T10:00:05+00:00',
}

const runCheck = () =>
  fireEvent.click(screen.getByRole('button', { name: /run full check/i }))

describe('DdFullCheckPanel', () => {
  beforeEach(() => {
    requestJson.mockReset()
    requestJson.mockResolvedValue(fullCheckResponse)
  })

  it('disables the run button until a case is selected', () => {
    renderWithProviders(<DdFullCheckPanel caseId="" />)
    expect(screen.getByRole('button', { name: /run full check/i })).toBeDisabled()
    expect(screen.getByText('Select or create a case first.')).toBeInTheDocument()
  })

  it('renders the consolidated risk headline after a successful run', async () => {
    renderWithProviders(<DdFullCheckPanel caseId="case-1" subjectLabel="Test Subject" />)
    runCheck()

    expect(await screen.findByText('Low risk - 4 hits across 8 sources')).toBeInTheDocument()
    expect(screen.getByText(/3 of 8 sources returned data\./)).toBeInTheDocument()
    expect(requestJson).toHaveBeenCalledWith('/due-diligence/cases/case-1/full-check', {
      method: 'POST',
      payload: {},
    })
  })

  it('renders all eight sources including the unavailable ones', async () => {
    renderWithProviders(<DdFullCheckPanel caseId="case-1" />)
    runCheck()

    await screen.findByText('Wikidata')
    fullCheckResponse.sources.forEach((row) => {
      expect(screen.getByText(row.label)).toBeInTheDocument()
    })
  })

  it('shows the setup detail for a not-configured source instead of hiding it', async () => {
    renderWithProviders(<DdFullCheckPanel caseId="case-1" />)
    runCheck()

    expect(
      await screen.findByText(
        'Not configured: set OPENSANCTIONS_API_KEY to enable this source.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Blocked: no identification code recorded for this case.'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Needs setup')).toHaveLength(3)
  })

  it('distinguishes a failed source from one that simply found nothing', async () => {
    renderWithProviders(<DdFullCheckPanel caseId="case-1" />)
    runCheck()

    await screen.findByText('Wikidata')
    expect(screen.getByText('Could not run')).toBeInTheDocument()
    expect(screen.getByText('GDELT returned HTTP 429.')).toBeInTheDocument()
    expect(screen.getByText('Nothing found')).toBeInTheDocument()
    expect(screen.getByText('No asset declarations matched this subject.')).toBeInTheDocument()
  })

  it('surfaces the real error message when the call fails', async () => {
    requestJson.mockRejectedValue(new Error('503 Service Unavailable'))
    renderWithProviders(<DdFullCheckPanel caseId="case-1" />)
    runCheck()

    expect(await screen.findByText('503 Service Unavailable')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run full check/i })).toBeEnabled(),
    )
  })
})
