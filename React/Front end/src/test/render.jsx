import React from 'react'
import { render } from '@testing-library/react'
import { MantineProvider } from '@mantine/core'
import { theme } from '../theme'

export function renderWithProviders(ui, options) {
  return render(ui, {
    wrapper: ({ children }) => (
      <MantineProvider theme={theme} defaultColorScheme="light">
        {children}
      </MantineProvider>
    ),
    ...options,
  })
}
