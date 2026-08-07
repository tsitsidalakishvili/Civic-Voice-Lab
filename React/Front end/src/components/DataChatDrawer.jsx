import { useEffect, useRef, useState } from 'react'
import { Button, Group, PasswordInput, Textarea } from '@mantine/core'
import { IconKey, IconSend, IconThumbDown, IconThumbUp } from '@tabler/icons-react'
import { Bar } from 'react-chartjs-2'
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { requestJson } from '../services/api'

ChartJS.register(BarElement, CategoryScale, Legend, LinearScale, Tooltip)

const SUGGESTIONS = [
  'How many members and supporters do we have?',
  'Which skills are most common among members?',
  'How many people registered for events this year?',
]

const OPENAI_KEY_STORAGE = 'fs_openai_api_key'
const CHART_COLORS = ['#2563eb', '#0ea5e9', '#14b8a6']

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)

const formatCell = (value) => {
  if (value == null) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const buildChart = (rows) => {
  if (!Array.isArray(rows) || rows.length === 0 || rows.length > 20) return null
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row || {})))]
  const numericKeys = keys.filter((key) => rows.some((row) => isNumber(row?.[key])))
  if (!numericKeys.length) return null

  if (rows.length === 1 && numericKeys.length >= 2) {
    return {
      labels: numericKeys.slice(0, 8),
      datasets: [
        {
          label: 'Value',
          data: numericKeys.slice(0, 8).map((key) => rows[0][key]),
          backgroundColor: '#2563eb',
          borderRadius: 6,
        },
      ],
    }
  }

  const labelKey = keys.find((key) => rows.some((row) => typeof row?.[key] === 'string'))
  if (!labelKey || rows.length < 2) return null
  const usableNumericKeys = numericKeys.filter((key) => key !== labelKey).slice(0, 3)
  if (!usableNumericKeys.length) return null
  return {
    labels: rows.map((row, index) => formatCell(row?.[labelKey]) || `Row ${index + 1}`),
    datasets: usableNumericKeys.map((key, index) => ({
      label: key,
      data: rows.map((row) => (isNumber(row?.[key]) ? row[key] : 0)),
      backgroundColor: CHART_COLORS[index],
      borderRadius: 6,
    })),
  }
}

function DataChatResults({ rows }) {
  if (!Array.isArray(rows) || !rows.length) return null
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row || {})))].slice(0, 8)
  const chart = buildChart(rows)
  const visibleRows = rows.slice(0, 20)
  return (
    <div className="data-chat__results">
      {chart ? (
        <div className="data-chat__chart">
          <Bar
            data={chart}
            options={{
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { display: chart.datasets.length > 1 } },
              scales: { y: { beginAtZero: true } },
            }}
          />
        </div>
      ) : null}
      <div className="data-chat__table-wrap">
        <table className="data-chat__table">
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {visibleRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => <td key={column}>{formatCell(row?.[column])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > visibleRows.length ? (
        <span className="data-chat__results-note">Showing the first {visibleRows.length} rows.</span>
      ) : null}
    </div>
  )
}

const readStoredOpenAiKey = () => {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(OPENAI_KEY_STORAGE) || '').trim()
}

export function DataChatPanel() {
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
          answerId: result?.answerId || '',
          feedback: '',
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

  const setFeedback = async (index, feedback) => {
    const message = messages[index]
    if (!message?.answerId || message.feedbackSaving) return
    setMessages((prev) =>
      prev.map((item, itemIndex) =>
        itemIndex === index ? { ...item, feedbackSaving: true, feedbackError: '' } : item,
      ),
    )
    try {
      await requestJson(`/data-chat/answers/${message.answerId}/feedback`, {
        method: 'PUT',
        payload: { feedback },
      })
      setMessages((prev) =>
        prev.map((item, itemIndex) =>
          itemIndex === index ? { ...item, feedback, feedbackSaving: false } : item,
        ),
      )
    } catch (err) {
      setMessages((prev) =>
        prev.map((item, itemIndex) =>
          itemIndex === index
            ? { ...item, feedbackSaving: false, feedbackError: err?.message || 'Could not save feedback.' }
            : item,
        ),
      )
    }
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    ask(draft)
  }

  return (
    <div className="data-chat data-chat--inline">
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
              {message.role === 'assistant' && !message.isError ? (
                <DataChatResults rows={message.rows} />
              ) : null}
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
              {message.role === 'assistant' && message.answerId && !message.isError ? (
                <div className="data-chat__reactions" aria-label="Rate this answer">
                  <button
                    type="button"
                    className={message.feedback === 'correct' ? 'is-active' : ''}
                    onClick={() => setFeedback(index, 'correct')}
                    disabled={message.feedbackSaving}
                    aria-label="Mark answer as correct"
                    title="Correct — use this logic for similar questions"
                  >
                    <IconThumbUp size={16} />
                  </button>
                  <button
                    type="button"
                    className={message.feedback === 'incorrect' ? 'is-active is-negative' : ''}
                    onClick={() => setFeedback(index, 'incorrect')}
                    disabled={message.feedbackSaving}
                    aria-label="Mark answer as incorrect"
                    title="Incorrect — do not learn from this answer"
                  >
                    <IconThumbDown size={16} />
                  </button>
                  {message.feedback ? <span>Feedback saved</span> : null}
                  {message.feedbackError ? <span className="data-chat__reaction-error">{message.feedbackError}</span> : null}
                </div>
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
  )
}
