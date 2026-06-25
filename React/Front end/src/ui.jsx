import React, { cloneElement, isValidElement, useId } from 'react'
import {
  ActionIcon,
  Badge,
  Card,
  Group,
  Progress,
  Select,
  SimpleGrid,
  Text,
  ThemeIcon,
  Tooltip,
} from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'

export function PageHeader({ title, description, eyebrow, actions, meta, children, className, ...rest }) {
  return (
    <header className={`page-header ${className || ''}`.trim()} {...rest}>
      <div className="page-header__text">
        {eyebrow ? <span className="page-header__eyebrow">{eyebrow}</span> : null}
        <h1 className="page-header__title">{title}</h1>
        {description ? <p className="page-header__desc">{description}</p> : null}
        {children}
      </div>
      {meta ? <div className="page-header__meta">{meta}</div> : null}
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  )
}

export function FormSection({ title, description, actions, children }) {
  return (
    <section className="form-section">
      {(title || description || actions) && (
        <div className="form-section__header">
          <div>
            {title ? <h4 className="form-section__title">{title}</h4> : null}
            {description ? <p className="form-section__desc">{description}</p> : null}
          </div>
          {actions ? <div className="form-section__actions">{actions}</div> : null}
        </div>
      )}
      <div className="form-section__body">{children}</div>
    </section>
  )
}

export function ModuleFlow({
  title,
  summary,
  steps = [],
  activeStepId,
  onStepSelect,
  actions,
}) {
  return (
    <section className="module-flow">
      <div className="module-flow__header">
        <div>
          <span className="module-flow__eyebrow">How it works</span>
          <h3>{title}</h3>
          {summary ? <p className="muted">{summary}</p> : null}
        </div>
        {actions ? <div className="module-flow__actions">{actions}</div> : null}
      </div>
      <div className="module-flow__steps">
        {steps.map((step, index) => {
          const isActive = activeStepId && step.id === activeStepId
          const isClickable = Boolean(step.id && onStepSelect)
          const StepTag = isClickable ? 'button' : 'div'
          return (
            <StepTag
              key={step.id || `${step.label}-${index}`}
              type={isClickable ? 'button' : undefined}
              className={`module-flow__step ${isActive ? 'is-active' : ''}`}
              onClick={isClickable ? () => onStepSelect(step.id) : undefined}
              aria-pressed={isClickable ? isActive : undefined}
            >
              <div className="module-flow__index">{index + 1}</div>
              <div>
                <div className="module-flow__label">{step.label}</div>
                {step.description ? (
                  <div className="module-flow__desc">{step.description}</div>
                ) : null}
              </div>
            </StepTag>
          )
        })}
      </div>
    </section>
  )
}

export function InfoHint({ text, label = 'More information' }) {
  if (!text) return null
  return (
    <Tooltip label={text} withArrow position="top">
      <ActionIcon
        className="info-hint"
        variant="light"
        size="sm"
        aria-label={label}
      >
        <IconInfoCircle size={16} stroke={1.5} />
      </ActionIcon>
    </Tooltip>
  )
}

export function InfoBox({ title, summary, hint, tone = 'info', actions, children }) {
  return (
    <div className={`info-box info-box--${tone}`}>
      <div className="info-box__header">
        <h4>{title}</h4>
        {hint ? <InfoHint text={hint} /> : null}
      </div>
      {summary ? <p className="muted">{summary}</p> : null}
      {children}
      {actions ? <div className="info-box__actions">{actions}</div> : null}
    </div>
  )
}

export function Field({ id, label, helper, required, error, children, className }) {
  const reactId = useId()
  const fieldId = id || reactId
  const helperId = helper ? `${fieldId}-help` : undefined
  const errorId = error ? `${fieldId}-error` : undefined
  const describedBy = [helperId, errorId].filter(Boolean).join(' ') || undefined
  const child = isValidElement(children)
    ? cloneElement(children, {
        id: fieldId,
        'aria-describedby': describedBy,
        'aria-invalid': Boolean(error) || undefined,
      })
    : children

  return (
    <div className={`field ${className || ''}`.trim()}>
      {label ? (
        <label className="label" htmlFor={fieldId}>
          {label}
          {required ? <span className="required">*</span> : null}
        </label>
      ) : null}
      {child}
      {helper ? (
        <div className="field__helper" id={helperId}>
          {helper}
        </div>
      ) : null}
      {error ? (
        <div className="field__error" id={errorId}>
          {error}
        </div>
      ) : null}
    </div>
  )
}

export function StatusMessage({ tone = 'info', message, role }) {
  if (!message) return null
  const computedRole = role || (tone === 'error' ? 'alert' : 'status')
  const live = tone === 'error' ? 'assertive' : 'polite'
  return (
    <div className={`status-message status-message--${tone}`} role={computedRole} aria-live={live}>
      {message}
    </div>
  )
}

export function LanguageSelect({
  language,
  onLanguageChange,
  languages,
  label = 'Language',
  hideLabel = false,
  className,
}) {
  const selectId = useId()
  const options = (languages || []).map((lang) => ({
    value: lang.id,
    label: lang.label,
  }))
  return (
    <Select
      className={`language-select ${className || ''}`.trim()}
      data={options}
      value={language}
      onChange={(value) => onLanguageChange?.(value || '')}
      label={hideLabel ? undefined : label}
      aria-label={hideLabel ? label : undefined}
      placeholder={label}
      comboboxProps={{ withinPortal: false }}
    />
  )
}

export function CivicStatGrid({ title, description, items = [], action, className }) {
  if (!items.length) return null
  return (
    <Card className={`civic-stat-grid ${className || ''}`.trim()}>
      {(title || description || action) && (
        <Group justify="space-between" align="flex-start" mb="md" wrap="wrap">
          <div>
            {title ? (
              <Text fw={600} size="lg">
                {title}
              </Text>
            ) : null}
            {description ? (
              <Text c="dimmed" size="sm">
                {description}
              </Text>
            ) : null}
          </div>
          {action}
        </Group>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing="md">
        {items.map((item, index) => (
          <Card key={`${item.label}-${index}`} radius="lg" withBorder>
            <Group justify="space-between" align="center">
              <div>
                <Text size="xs" c="dimmed">
                  {item.label}
                </Text>
                <Text fw={600} size="xl">
                  {item.value}
                </Text>
              </div>
              {item.icon ? (
                <ThemeIcon
                  color={item.color || 'civic'}
                  variant={item.variant || 'light'}
                  size="lg"
                  radius="md"
                >
                  {item.icon}
                </ThemeIcon>
              ) : null}
            </Group>
            {item.badge ? (
              <Badge mt="sm" variant="light" color={item.badgeColor || 'civic'}>
                {item.badge}
              </Badge>
            ) : null}
            {item.note ? (
              <Text c="dimmed" size="xs" mt="xs">
                {item.note}
              </Text>
            ) : null}
            {typeof item.progress === 'number' ? (
              <Progress value={item.progress} mt="sm" radius="xl" />
            ) : null}
          </Card>
        ))}
      </SimpleGrid>
    </Card>
  )
}

export function MobileNavDrawer({
  open,
  onClose,
  modules,
  activeModuleId,
  onSelect,
  language,
  onLanguageChange,
  t,
  languages,
  currentModuleLabel,
}) {
  if (!open) return null

  return (
    <div className="mobile-drawer" role="dialog" aria-modal="true" aria-label="Module navigation">
      <div className="mobile-drawer__backdrop" onClick={onClose} aria-hidden="true" />
      <div className="mobile-drawer__panel">
        <div className="mobile-drawer__header">
          <div>
            <span className="page-header__eyebrow">{t ? t('modules.title') : 'Modules'}</span>
            <h3>Navigate</h3>
            <p className="muted">Choose a module to continue where you left off.</p>
          </div>
          <button className="button-secondary" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="mobile-drawer__current">
          <span className="pill">Current module</span>
          <h4>{currentModuleLabel}</h4>
        </div>
        <div className="mobile-drawer__section">
          <label className="label">{t ? t('language.label') : 'Language'}</label>
          <select
            className="select"
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            {(languages || []).map((lang) => (
              <option key={lang.id} value={lang.id}>
                {lang.label}
              </option>
            ))}
          </select>
        </div>
        <div className="mobile-drawer__nav">
          {modules.map((module) => (
            <button
              key={module.id}
              type="button"
              className={
                module.id === activeModuleId
                  ? 'module-nav__item module-nav__item--active'
                  : 'module-nav__item'
              }
              onClick={() => onSelect(module.id)}
            >
              <span className="module-nav__label">{module.label}</span>
              <span className="module-nav__desc">{module.description}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

