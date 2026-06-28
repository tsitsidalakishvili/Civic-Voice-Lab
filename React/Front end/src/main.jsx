import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import { MantineProvider, localStorageColorSchemeManager } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import '@mantine/spotlight/styles.css'
import './index.css'
import App from './app/App.jsx'
import { theme } from './theme'

const colorSchemeManager = localStorageColorSchemeManager({ key: 'fs_color_scheme' })

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MantineProvider theme={theme} colorSchemeManager={colorSchemeManager} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <App />
      <Analytics />
    </MantineProvider>
  </StrictMode>,
)

