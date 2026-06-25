import { createTheme, rem } from '@mantine/core'

export const theme = createTheme({
  fontFamily: 'Inter, Sylfaen, "Segoe UI", Arial, system-ui, sans-serif',
  headings: { fontFamily: 'Inter, Sylfaen, "Segoe UI", Arial, system-ui, sans-serif' },
  primaryColor: 'civic',
  primaryShade: { light: 6, dark: 4 },
  defaultRadius: 'md',
  colors: {
    civic: [
      '#eef4ff',
      '#dbe7ff',
      '#b6ceff',
      '#8fb4ff',
      '#6a9bff',
      '#4f87f2',
      '#3a73d4',
      '#2f60b1',
      '#274f92',
      '#214178',
    ],
  },
  radius: {
    xs: rem(6),
    sm: rem(8),
    md: rem(12),
    lg: rem(16),
    xl: rem(20),
  },
  shadows: {
    sm: '0 1px 3px rgba(15, 23, 42, 0.12)',
    md: '0 12px 24px rgba(15, 23, 42, 0.12)',
    lg: '0 18px 40px rgba(15, 23, 42, 0.16)',
  },
  components: {
    Card: {
      defaultProps: {
        withBorder: true,
        radius: 'lg',
        shadow: 'sm',
        padding: 'md',
      },
    },
    Paper: {
      defaultProps: {
        withBorder: true,
        radius: 'lg',
        p: 'md',
      },
    },
  },
})


