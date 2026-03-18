import React from 'react'
import { render, screen } from '@testing-library/react'
import { AudienceDiscoveryPage } from '../AudienceDiscoveryPage.jsx'

describe('AudienceDiscoveryPage', () => {
  it('renders run discovery section', () => {
    render(<AudienceDiscoveryPage t={(key) => key} />)
    expect(screen.getByText('module.audienceDiscovery')).toBeInTheDocument()
    expect(screen.getByText('Run discovery')).toBeInTheDocument()
  })
})
