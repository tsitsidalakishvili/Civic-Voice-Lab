import React from 'react'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/render.jsx'
import { AudienceDiscoveryPage } from '../AudienceDiscoveryPage.jsx'

describe('AudienceDiscoveryPage', () => {
  it('renders run discovery section', () => {
    renderWithProviders(<AudienceDiscoveryPage t={(key) => key} />)
    expect(screen.getByText('module.audienceDiscovery')).toBeInTheDocument()
    expect(screen.getByText('Discovery pulse')).toBeInTheDocument()
  })
})


