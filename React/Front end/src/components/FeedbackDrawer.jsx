import { useState } from 'react'
import { Button, Drawer, Group, Stack, TextInput, Textarea } from '@mantine/core'
import { requestJson } from '../services/api'
import { FormSection, StatusMessage } from '../ui'

export function FeedbackDrawer({ opened, onClose, t, activeModuleLabel }) {
  const [form, setForm] = useState({ name: '', email: '', message: '' })
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setStatus('')
    setStatusTone('info')
    setError('')
    if (!form.message.trim()) {
      setError(t('feedback.errorEmpty'))
      return
    }
    setSending(true)
    try {
      const response = await requestJson('/crm/feedback', {
        method: 'POST',
        payload: {
          name: form.name.trim(),
          email: form.email.trim(),
          message: form.message.trim(),
          page: activeModuleLabel || 'App',
          channel: 'sidebar_feedback',
        },
      })
      if (response?.email_status === 'sent') {
        setStatus(t('feedback.statusSent'))
        setStatusTone('success')
      } else if (response?.email_status === 'failed') {
        setStatus(t('feedback.statusFailed'))
        setStatusTone('error')
      } else if (response?.email_status === 'not_configured') {
        setStatus(t('feedback.statusNotConfigured'))
        setStatusTone('info')
      } else {
        setStatus(t('feedback.statusSaved'))
        setStatusTone('success')
      }
      setForm({ name: '', email: '', message: '' })
    } catch (err) {
      setError(err.message || t('feedback.errorSend'))
    } finally {
      setSending(false)
    }
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="md"
      title={t('feedback.title')}
    >
      <FormSection
        title={t('feedback.title')}
        description="Share what you were trying to do, what happened, and what you expected."
      >
        <form className="stack form-shell" onSubmit={handleSubmit} aria-busy={sending}>
          <Stack>
            <TextInput
              label={t('feedback.name')}
              placeholder="Jane Doe"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
            />
            <TextInput
              label={t('feedback.email')}
              placeholder="jane@email.com"
              type="email"
              value={form.email}
              onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
            />
            <Textarea
              label={t('feedback.message')}
              placeholder="Tell us what happened..."
              value={form.message}
              onChange={(e) => setForm((prev) => ({ ...prev, message: e.target.value }))}
              minRows={5}
              required
            />
            <Group justify="flex-end">
              <Button type="submit" loading={sending}>
                {sending ? t('feedback.sending') : t('feedback.send')}
              </Button>
            </Group>
          </Stack>
          <StatusMessage tone="error" message={error} />
          <StatusMessage tone={statusTone} message={status} />
        </form>
      </FormSection>
    </Drawer>
  )
}
