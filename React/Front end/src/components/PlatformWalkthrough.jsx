import { useEffect, useMemo, useState } from 'react'
import { ActionIcon, Button, Group, Kbd, Menu, Text } from '@mantine/core'
import { IconArrowLeft, IconArrowRight, IconPlayerSkipForward, IconX } from '@tabler/icons-react'
import { buildModuleWalkthroughScenario, hubWalkthroughScenario, taskWalkthroughScenarios } from '../config/walkthroughScenarios'

const tourStorageKey = 'fs_walkthrough_seen'
const placementOffset = 16

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function getTooltipPosition(rect, placement) {
  const width = Math.min(400, window.innerWidth - 32)
  const height = 242
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2

  if (placement === 'left') {
    return {
      width,
      left: clamp(rect.left - width - placementOffset, 16, window.innerWidth - width - 16),
      top: clamp(centerY - height / 2, 16, window.innerHeight - height - 16),
    }
  }

  if (placement === 'right') {
    return {
      width,
      left: clamp(rect.right + placementOffset, 16, window.innerWidth - width - 16),
      top: clamp(centerY - height / 2, 16, window.innerHeight - height - 16),
    }
  }

  if (placement === 'top') {
    return {
      width,
      left: clamp(centerX - width / 2, 16, window.innerWidth - width - 16),
      top: clamp(rect.top - height - placementOffset, 16, window.innerHeight - height - 16),
    }
  }

  return {
    width,
    left: clamp(centerX - width / 2, 16, window.innerWidth - width - 16),
    top: clamp(rect.bottom + placementOffset, 16, window.innerHeight - height - 16),
  }
}

function resolveTarget(selector) {
  if (!selector) return null
  return document.querySelector(selector)
}

function getSpotlightStyle(rect, padding = 8) {
  const left = clamp(rect.left - padding, 8, window.innerWidth - 32)
  const top = clamp(rect.top - padding, 8, window.innerHeight - 32)
  const right = clamp(rect.right + padding, left + 24, window.innerWidth - 8)
  const bottom = clamp(rect.bottom + padding, top + 24, window.innerHeight - 8)

  return {
    left,
    top,
    width: right - left,
    height: bottom - top,
  }
}

export function PlatformWalkthrough({
  activeModule,
  activeModuleConfig,
  onOpenModuleHub,
  onModuleChange,
  onModuleSectionChange,
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [targetRect, setTargetRect] = useState(null)
  const [tourKey, setTourKey] = useState('context')

  const steps = useMemo(() => {
    if (tourKey.startsWith('task:')) {
      return taskWalkthroughScenarios[tourKey.replace('task:', '')]?.steps || hubWalkthroughScenario
    }
    if (tourKey === 'platform') return hubWalkthroughScenario
    if (activeModule) return buildModuleWalkthroughScenario(activeModule, activeModuleConfig)
    return hubWalkthroughScenario
  }, [activeModule, activeModuleConfig, tourKey])

  const currentStep = steps[stepIndex]
  const canGoBack = stepIndex > 0
  const isLastStep = stepIndex >= steps.length - 1

  const closeTour = () => {
    setIsOpen(false)
    setStepIndex(0)
    setTargetRect(null)
    localStorage.setItem(tourStorageKey, '1')
  }

  const startTour = (nextTourKey = 'context') => {
    setTourKey(nextTourKey)
    setTargetRect(null)
    setStepIndex(0)
    setIsOpen(true)
  }

  useEffect(() => {
    if (!isOpen || !currentStep) return undefined

    let cancelled = false
    let scrollTimeout = 0
    let settleTimeout = 0
    let frame = 0

    setTargetRect(null)

    if (currentStep.moduleId) {
      onModuleChange?.(currentStep.moduleId)
    }

    if (currentStep.sectionValue) {
      onModuleSectionChange?.(currentStep.moduleId || activeModule?.id, currentStep.sectionValue)
    }

    const measureTarget = () => {
      if (cancelled) return
      const element = resolveTarget(currentStep.selector)
      if (!element) return
      setTargetRect(element.getBoundingClientRect())
    }

    const scheduleMeasure = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => {
        frame = window.requestAnimationFrame(measureTarget)
      })
    }

    const scrollTargetIntoView = () => {
      if (cancelled) return
      const element = resolveTarget(currentStep.selector)
      if (!element) return
      element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' })
      scheduleMeasure()
      settleTimeout = window.setTimeout(scheduleMeasure, 520)
    }

    scrollTimeout = window.setTimeout(
      scrollTargetIntoView,
      currentStep.moduleId ? 520 : currentStep.sectionValue ? 320 : 120,
    )
    window.addEventListener('resize', scheduleMeasure)
    window.addEventListener('scroll', scheduleMeasure, true)

    return () => {
      cancelled = true
      window.clearTimeout(scrollTimeout)
      window.clearTimeout(settleTimeout)
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', scheduleMeasure)
      window.removeEventListener('scroll', scheduleMeasure, true)
    }
  }, [activeModule?.id, currentStep, isOpen, onModuleChange, onModuleSectionChange])

  useEffect(() => {
    if (!isOpen) return undefined
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') closeTour()
      if (event.key === 'ArrowRight') setStepIndex((prev) => Math.min(prev + 1, steps.length - 1))
      if (event.key === 'ArrowLeft') setStepIndex((prev) => Math.max(prev - 1, 0))
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, steps.length])

  const tooltipStyle = targetRect ? getTooltipPosition(targetRect, currentStep?.placement) : {}
  const spotlightStyle = targetRect ? getSpotlightStyle(targetRect, currentStep?.padding || 8) : {}

  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <Button
            variant="light"
            size="xs"
            leftSection={<IconPlayerSkipForward size={14} />}
            data-tour="walkthrough-launch"
          >
            Walkthrough
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>General</Menu.Label>
          <Menu.Item onClick={() => startTour('platform')}>Platform overview</Menu.Item>
          {activeModule ? (
            <Menu.Item onClick={() => startTour('context')}>Current module</Menu.Item>
          ) : null}
          <Menu.Divider />
          <Menu.Label>Workflow tours</Menu.Label>
          {Object.entries(taskWalkthroughScenarios).map(([key, scenario]) => (
            <Menu.Item key={key} onClick={() => startTour(`task:${key}`)}>
              {scenario.label}
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>

      {isOpen ? (
        <div className="walkthrough" role="dialog" aria-modal="true" aria-labelledby="walkthrough-title">
          <div className="walkthrough__scrim" />
          {targetRect ? <div className="walkthrough__spotlight" style={spotlightStyle} /> : null}
          <div className="walkthrough__card" style={tooltipStyle}>
            <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
              <div>
                <Text size="xs" c="dimmed" fw={700} tt="uppercase">
                  Step {stepIndex + 1} of {steps.length}
                </Text>
                <h2 id="walkthrough-title">{currentStep?.title}</h2>
              </div>
              <ActionIcon variant="subtle" color="gray" onClick={closeTour} aria-label="Close walkthrough">
                <IconX size={18} />
              </ActionIcon>
            </Group>
            <p>{currentStep?.body}</p>
            <Group justify="space-between" align="center" mt="md" gap="sm">
              <Group gap={6} className="walkthrough__keys">
                <Kbd>Esc</Kbd>
                <Text size="xs" c="dimmed">close</Text>
              </Group>
              <Group gap="xs">
                {activeModule && stepIndex === 0 ? (
                  <Button variant="subtle" size="xs" onClick={onOpenModuleHub}>
                    Open hub
                  </Button>
                ) : null}
                <Button variant="subtle" size="xs" onClick={closeTour}>
                  Skip
                </Button>
                <Button
                  variant="light"
                  size="xs"
                  leftSection={<IconArrowLeft size={14} />}
                  disabled={!canGoBack}
                  onClick={() => setStepIndex((prev) => Math.max(prev - 1, 0))}
                >
                  Back
                </Button>
                <Button
                  size="xs"
                  rightSection={isLastStep ? null : <IconArrowRight size={14} />}
                  onClick={() => {
                    if (isLastStep) closeTour()
                    else setStepIndex((prev) => Math.min(prev + 1, steps.length - 1))
                  }}
                >
                  {isLastStep ? 'Done' : 'Next'}
                </Button>
              </Group>
            </Group>
          </div>
        </div>
      ) : null}
    </>
  )
}
