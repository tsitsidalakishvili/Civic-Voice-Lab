import { useEffect, useRef, useState } from 'react'
import { Button, Drawer, Group, PasswordInput, Textarea } from '@mantine/core'
import { IconKey, IconSend } from '@tabler/icons-react'
import { requestJson } from '../services/api'

const SUGGESTIONS = [
  'How many members and supporters do we have?',
  'Which skills are most common among members?',
  'How many people registered for events this year?',
]

const OPENAI_KEY_STORAGE = 'fs_openai_api_key'

const readStoredOpenAiKey = () => {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(OPENAI_KEY_STORAGE) || '').trim()
}

export function DataChatDrawer({ opened, onClose }) {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [asking, setAsking] = useState(false)
  const [apiKey, setApiKey] = useState(readStoredOpenAiKey)
  const [showKeyInput, setShowKeyInput] = useState(false)
  const scrollRef = useRef(null)

  const saveApiKey = (value) => {
    const trimmed = String(value || '').trim()
    setApiKey(trimmed)
    if (typeof window === 'undefined') return
    if (trimmed) window.localStorage.setItem(OPENAI_KEY_STORAGE, trimmed)
    else window.localStorage.removeItem(OPENAI_KEY_STORAGE)
  }

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, asking])

  const ask = async (text) => {
    const question = String(text || '').trim()
    if (!question || asking) return
    setDraft('')
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setAsking(true)
    try {
      const result = await requestJson('/data-chat/ask', {
        method: 'POST',
        payload: { question, apiKey: apiKey || '' },
      })
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: result?.answer || 'No answer returned.',
          cypher: result?.cypher || '',
          rows: Array.isArray(result?.rows) ? result.rows : [],
          rowCount: result?.rowCount ?? 0,
        },
      ])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: err?.message || 'Something went wrong while answering.',
          isError: true,
        },
      ])
    } finally {
      setAsking(false)
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    ask(draft)
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="md"
      title="Ask your data"
    >
      <div className="data-chat">
        <p className="muted data-chat__intro">
          Ask a question about the database in plain language. Answers are computed with a
          live database query — open “How it was answered” under any reply to audit it.
        </p>
        <div className="data-chat__settings">
          <button
            className="button-secondary button-secondary--small"
            type="button"
            onClick={() => setShowKeyInput((prev) => !prev)}
          >
            <IconKey size={14} />
            {apiKey ? 'OpenAI key saved' : 'Set OpenAI API key'}
          </button>
          {showKeyInput ? (
            <PasswordInput
              placeholder="sk-..."
              value={apiKey}
              onChange={(event) => saveApiKey(event.target.value)}
              description="Stored only in this browser and used for your questions. Leave empty to use the server's key."
            />
          ) : null}
        </div>
        <div className="data-chat__messages" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="data-chat__suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  className="button-secondary button-secondary--small"
                  type="button"
                  onClick={() => ask(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : null}
          {messages.map((message, index) => (
            <div
              key={index}
              className={`data-chat__bubble data-chat__bubble--${message.role} ${
                message.isError ? 'data-chat__bubble--error' : ''
              }`}
            >
              <div className="data-chat__text">{message.text}</div>
              {message.cypher ? (
                <details className="data-chat__details">
                  <summary>How it was answered ({message.rowCount} rows)</summary>
                  <pre className="code-block">{message.cypher}</pre>
                  {message.rows?.length ? (
                    <pre className="code-block">
                      {JSON.stringify(message.rows.slice(0, 10), null, 2)}
                    </pre>
                  ) : null}
                </details>
              ) : null}
            </div>
          ))}
          {asking ? (
            <div className="data-chat__bubble data-chat__bubble--assistant">
              <div className="data-chat__text muted">Querying the database...</div>
            </div>
          ) : null}
        </div>
        <form className="data-chat__composer" onSubmit={handleSubmit}>
          <Textarea
            placeholder="e.g. How many members joined this year?"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                ask(draft)
              }
            }}
            minRows={2}
            autosize
            maxRows={5}
            disabled={asking}
          />
          <Group justify="flex-end">
            <Button
              type="submit"
              leftSection={<IconSend size={16} />}
              loading={asking}
              disabled={!draft.trim()}
            >
              Ask
            </Button>
          </Group>
        </form>
      </div>
    </Drawer>
  )
}
