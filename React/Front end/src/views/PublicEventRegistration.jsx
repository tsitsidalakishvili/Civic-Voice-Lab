import { useEffect, useState } from 'react'
import { Button, Select, TextInput, Textarea } from '@mantine/core'
import { getJson, requestJson } from '../services/api'
import { Field, FormSection, LanguageSelect, StatusMessage } from '../ui'

export function PublicEventRegistration({ eventId, t, language, languages, onLanguageChange }) {
  const translate = t || ((key) => key)
  const [event, setEvent] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    phone: '',
    group: 'Supporter',
    notes: '',
  })
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    getJson(`/crm/events/detail?event_id=${encodeURIComponent(eventId)}`)
      .then((payload) => setEvent(payload))
      .catch((err) => setError(err.message || translate('event.notFound')))
  }, [eventId])

  const handleSubmit = async (eventAction) => {
    eventAction.preventDefault()
    if (!form.fullName.trim() || !form.email.trim()) {
      setStatus(translate('event.fullNameRequired'))
      setStatusTone('error')
      return
    }
    setStatus('')
    setStatusTone('info')
    setSubmitting(true)
    try {
      const [firstName, ...rest] = form.fullName.trim().split(/\s+/)
      await requestJson(`/crm/events/${eventId}/register`, {
        method: 'POST',
        payload: {
          person: {
            email: form.email.trim(),
            firstName,
            lastName: rest.join(' '),
            phone: form.phone.trim(),
            group: form.group,
          },
          status: 'Registered',
          notes: form.notes.trim(),
        },
      })
      setStatus(translate('event.thanks'))
      setStatusTone('success')
      setForm({ fullName: '', email: '', phone: '', group: 'Supporter', notes: '' })
    } catch (err) {
      setStatus(err.message || 'Registration failed.')
      setStatusTone('error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="module">
      <div className="page-language">
        <LanguageSelect
          language={language}
          languages={languages}
          onLanguageChange={onLanguageChange}
          label={translate('language.label')}
        />
      </div>
      <header className="module-header">
        <h2>{event?.name || translate('event.registrationTitle')}</h2>
        {event?.startDate ? <p>{event.startDate}</p> : null}
      </header>
      <StatusMessage tone="error" message={error} />
      {event ? (
        <form
          className="module-card module-card__wide form-shell"
          onSubmit={handleSubmit}
          aria-busy={submitting}
        >
          <FormSection
            title="Attendee details"
            description="Required fields are marked. Confirmation shows here after you submit."
          >
            <div className="form-grid">
              <Field
                id="event-full-name"
                label={translate('event.fullName')}
                helper="Required. Enter first and last name."
                required
              >
                <TextInput
                  placeholder="Aisha Khan"
                  value={form.fullName}
                  onChange={(evt) =>
                    setForm((prev) => ({ ...prev, fullName: evt.target.value }))
                  }
                  required
                />
              </Field>
              <Field
                id="event-email"
                label={translate('event.email')}
                helper="Required. We'll email a confirmation."
                required
              >
                <TextInput
                  type="email"
                  placeholder="aisha@email.com"
                  value={form.email}
                  onChange={(evt) =>
                    setForm((prev) => ({ ...prev, email: evt.target.value }))
                  }
                  required
                />
              </Field>
              <Field
                id="event-phone"
                label={translate('event.phone')}
                helper="Optional. Include for reminders."
              >
                <TextInput
                  placeholder="+995 555 123 456"
                  value={form.phone}
                  onChange={(evt) =>
                    setForm((prev) => ({ ...prev, phone: evt.target.value }))
                  }
                />
              </Field>
            </div>
          </FormSection>
          <FormSection
            title="Registration details"
            description="Optional details to help the organizers prepare."
          >
            <div className="form-grid">
              <Field id="event-group" label="Group" helper="Select the attendee type.">
                <Select
                  value={form.group}
                  onChange={(value) =>
                    setForm((prev) => ({ ...prev, group: value || '' }))
                  }
                  data={[
                    { value: 'Supporter', label: translate('event.groupSupporter') },
                    { value: 'Member', label: translate('event.groupMember') },
                  ]}
                />
              </Field>
              <Field
                id="event-notes"
                label={translate('event.notes')}
                helper="Optional notes"
              >
                <Textarea
                  placeholder="Accessibility needs, questions, or context..."
                  value={form.notes}
                  onChange={(evt) =>
                    setForm((prev) => ({ ...prev, notes: evt.target.value }))
                  }
                  minRows={4}
                />
              </Field>
            </div>
          </FormSection>
          <div className="form-actions">
            <Button type="submit" loading={submitting}>
              {submitting ? 'Submitting...' : translate('event.register')}
            </Button>
          </div>
          <StatusMessage tone={statusTone} message={status} />
        </form>
      ) : null}
    </section>
  )
}
