import { useMantineColorScheme, ActionIcon, Tooltip } from '@mantine/core'
import { IconSun, IconMoon } from '@tabler/icons-react'

export function ThemeToggle() {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()
  const isDark = colorScheme === 'dark'
  return (
    <Tooltip label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}>
      <ActionIcon
        variant="light"
        size="lg"
        onClick={toggleColorScheme}
        aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {isDark ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  )
}
