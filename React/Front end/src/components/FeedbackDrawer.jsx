import { useRef, useState } from 'react'
import { Button, Drawer, FileButton, Group, Stack, TextInput, Textarea } from '@mantine/core'
import { IconCamera, IconPhoto, IconX } from '@tabler/icons-react'
import { requestJson } from '../services/api'
import { FormSection, StatusMessage } from '../ui'

const MAX_SCREENSHOT_EDGE = 1600
const SCREENSHOT_JPEG_QUALITY = 0.85

/** Downscale large images so the payload stays small enough to store and email. */
function fileToScreenshotDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Could not read the image file.'))
    reader.onload = () => {
      const image = new Image()
      image.onerror = () => reject(new Error('Could not load the image.'))
      image.onload = () => {
        const scale = Math.min(
          1,
          MAX_SCREENSHOT_EDGE / Math.max(image.width, image.height),
        )
        if (scale >= 1 && String(reader.result).length < 1_500_000) {
          resolve(String(reader.result))
          return
        }
        const canvas = document.createElement('canvas')
        canvas.width = Math.max(1, Math.round(image.width * scale))
        canvas.height = Math.max(1, Math.round(image.height * scale))
        const context = canvas.getContext('2d')
        context.drawImage(image, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', SCREENSHOT_JPEG_QUALITY))
      }
      image.src = String(reader.result)
    }
    reader.readAsDataURL(file)
  })
}

export function FeedbackDrawer({ opened, onClose, t, activeModuleLabel }) {
  const [form, setForm] = useState({ name: '', email: '', message: '' })
  const [screenshot, setScreenshot] = useState('')
  const [screenshotError, setScreenshotError] = useState('')
  const [status, setStatus] = useState('')
  const [statusTone, setStatusTone] = useState('info')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const resetFileRef = useRef(null)
  const formRef = useRef(null)

  const attachScreenshot = async (file) => {
    if (!file) return
    setScreenshotError('')
    if (!String(file.type || '').startsWith('image/')) {
      setScreenshotError('Only image files can be attached.')
      return
    }
    try {
      const dataUrl = await fileToScreenshotDataUrl(file)
      setScreenshot(dataUrl)
    } catch (err) {
      setScreenshotError(err.message || 'Could not attach the screenshot.')
    }
  }

  const clearScreenshot = () => {
    setScreenshot('')
    setScreenshotError('')
    if (resetFileRef.current) resetFileRef.current()
  }

  const handlePaste = (event) => {
    const items = Array.from(event.clipboardData?.items || [])
    const imageItem = items.find((item) => item.type.startsWith('image/'))
    if (imageItem) {
      attachScreenshot(imageItem.getAsFile())
    }
  }

  const captureScreenshot = async () => {
    setScreenshotError('')
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setScreenshotError('Screen capture is not supported in this browser. Use Attach instead.')
      return
    }
    setCapturing(true)
    let stream
    // The drawer covers the page, so hide its portal while the frame is grabbed.
    let portalNode = formRef.current
    while (portalNode && portalNode.parentElement && portalNode.parentElement !== document.body) {
      portalNode = portalNode.parentElement
    }
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
        preferCurrentTab: true,
        selfBrowserSurface: 'include',
      })
      const video = document.createElement('video')
      video.srcObject = stream
      video.muted = true
      await video.play()
      await new Promise((resolve) => setTimeout(resolve, 400))
      if (portalNode) portalNode.style.visibility = 'hidden'
      await new Promise((resolve) => setTimeout(resolve, 200))
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 1280
      canvas.height = video.videoHeight || 720
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'))
      if (!blob) throw new Error('Could not capture the screen.')
      await attachScreenshot(new File([blob], 'screenshot.png', { type: 'image/png' }))
    } catch (err) {
      if (err?.name !== 'NotAllowedError') {
        setScreenshotError(err?.message || 'Screen capture failed. Use Attach instead.')
      }
    } finally {
      if (portalNode) portalNode.style.visibility = ''
      if (stream) stream.getTracks().forEach((track) => track.stop())
      setCapturing(false)
    }
  }

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
          screenshot: screenshot || '',
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
      clearScreenshot()
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
        <form ref={formRef} className="stack form-shell" onSubmit={handleSubmit} aria-busy={sending}>
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
              placeholder="Tell us what happened... (you can paste a screenshot here too)"
              value={form.message}
              onChange={(e) => setForm((prev) => ({ ...prev, message: e.target.value }))}
              onPaste={handlePaste}
              minRows={5}
              required
            />
            <div className="feedback-screenshot">
              <Group gap="sm">
                <Button
                  variant="light"
                  leftSection={<IconCamera size={16} />}
                  onClick={captureScreenshot}
                  loading={capturing}
                >
                  {capturing ? 'Capturing...' : 'Take screenshot'}
                </Button>
                <FileButton
                  resetRef={resetFileRef}
                  onChange={attachScreenshot}
                  accept="image/*"
                >
                  {(props) => (
                    <Button variant="light" leftSection={<IconPhoto size={16} />} {...props}>
                      {screenshot ? 'Replace screenshot' : 'Attach image'}
                    </Button>
                  )}
                </FileButton>
                {screenshot ? (
                  <Button
                    variant="subtle"
                    color="red"
                    leftSection={<IconX size={16} />}
                    onClick={clearScreenshot}
                  >
                    Remove
                  </Button>
                ) : null}
              </Group>
              <p className="muted feedback-screenshot__hint">
                Take a screenshot of this page, attach an image, or paste one into the message
                so we can see exactly what you mean.
              </p>
              {screenshot ? (
                <img
                  className="feedback-screenshot__preview"
                  src={screenshot}
                  alt="Screenshot preview"
                />
              ) : null}
              <StatusMessage tone="error" message={screenshotError} />
            </div>
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
