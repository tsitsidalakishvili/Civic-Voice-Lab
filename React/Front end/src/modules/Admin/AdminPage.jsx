import { useEffect, useState } from 'react'
import { getJson, requestJson } from '../../services/api'

const csvEscape = (value) => {
  if (value === null || value === undefined) return ''
  const text = String(value)
  if (text.includes('"') || text.includes(',') || text.includes('\n')) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

const toCsv = (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return ''
  const headers = Array.from(
    rows.reduce((acc, row) => {
      Object.keys(row || {}).forEach((key) => acc.add(key))
      return acc
    }, new Set()),
  )
  const lines = [headers.join(',')]
  rows.forEach((row) => {
    const line = headers.map((key) => csvEscape(row?.[key])).join(',')
    lines.push(line)
  })
  return lines.join('\n')
}

const downloadCsv = (filename, rows) => {
  const csv = toCsv(rows)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function AdminPage({ t }) {
  const translate = t || ((key, vars) => key)
  const [activeTab, setActiveTab] = useState('admin')
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState([])
  const [slackMessage, setSlackMessage] = useState(
    'Freedom Square Network is connected to Slack.',
  )
  const [slackError, setSlackError] = useState('')
  const [clearConfirm, setClearConfirm] = useState('')
  const [clearStatus, setClearStatus] = useState('')
  const [clearError, setClearError] = useState('')
  const [clearLoading, setClearLoading] = useState(false)
  const [deleteData, setDeleteData] = useState({
    tasks: [],
    events: [],
    segments: [],
    groups: [],
    conversations: [],
  })
  const [summary, setSummary] = useState(null)

  const loadAdminData = () => {
    setError('')
    Promise.all([
      getJson('/crm/admin/status'),
      getJson('/crm/admin/feedback'),
      getJson('/crm/tasks?limit=200'),
      getJson('/crm/events?limit=200'),
      getJson('/crm/segments'),
      getJson('/crm/whatsapp-groups'),
      getJson('/conversations'),
      getJson('/crm/summary'),
    ])
      .then(
        ([
          statusPayload,
          feedbackPayload,
          tasksPayload,
          eventsPayload,
          segmentsPayload,
          groupsPayload,
          conversationsPayload,
          summaryPayload,
        ]) => {
          setStatus(statusPayload)
          setFeedback(Array.isArray(feedbackPayload) ? feedbackPayload : [])
          setDeleteData({
            tasks: Array.isArray(tasksPayload) ? tasksPayload : [],
            events: Array.isArray(eventsPayload) ? eventsPayload : [],
            segments: Array.isArray(segmentsPayload) ? segmentsPayload : [],
            groups: Array.isArray(groupsPayload) ? groupsPayload : [],
            conversations: Array.isArray(conversationsPayload) ? conversationsPayload : [],
          })
          setSummary(summaryPayload)
        },
      )
      .catch((err) => setError(err.message || 'Unable to load admin data.'))
  }

  useEffect(() => {
    loadAdminData()
  }, [])

  const handleSlackTest = async () => {
    setSlackError('')
    try {
      await requestJson('/crm/admin/slack-test', {
        method: 'POST',
        payload: { message: slackMessage },
      })
    } catch (err) {
      setSlackError(err.message || 'Slack test failed.')
    }
  }

  const handleDelete = async (type, id) => {
    setError('')
    try {
      if (type === 'task') {
        await requestJson(`/crm/tasks/${id}`, { method: 'DELETE' })
      } else if (type === 'event') {
        await requestJson(`/crm/events/${id}`, { method: 'DELETE' })
      } else if (type === 'segment') {
        await requestJson(`/crm/segments/${id}`, { method: 'DELETE' })
      } else if (type === 'group') {
        await requestJson(`/crm/whatsapp-groups/${id}`, { method: 'DELETE' })
      } else if (type === 'conversation') {
        await requestJson(`/conversations/${id}`, { method: 'DELETE' })
      }
      loadAdminData()
    } catch (err) {
      setError(err.message || 'Delete failed.')
    }
  }

  const handleClearDb = async () => {
    setClearError('')
    setClearStatus('')
    const confirmText = clearConfirm.trim()
    if (confirmText !== 'CLEAR AURA DB') {
      setClearError("Type 'CLEAR AURA DB' to confirm.")
      return
    }
    setClearLoading(true)
    try {
      const result = await requestJson('/crm/admin/clear-db', {
        method: 'POST',
        payload: { confirm: confirmText },
      })
      const nodes = result?.deleted_nodes ?? 0
      const rels = result?.deleted_relationships ?? 0
      setClearStatus(`Database cleared. Deleted ${nodes} nodes and ${rels} relationships.`)
      setClearConfirm('')
      loadAdminData()
    } catch (err) {
      setClearError(err.message || 'Clear DB failed.')
    } finally {
      setClearLoading(false)
    }
  }

  const handleExportSummary = async () => {
    setError('')
    try {
      const rows = await getJson('/crm/people/summary?limit=5000')
      downloadCsv('people_summary.csv', rows)
    } catch (err) {
      setError(err.message || 'Export failed.')
    }
  }

  return (
    <section className="module">
      <header className="module-header">
        <div className="module-header__text">
          <h2>{translate('settings.header.title')}</h2>
          <p>{translate('settings.header.subtitle')}</p>
        </div>
        <div className="module-header__meta">
          <div className="module-header__metric">
            <span>Neo4j</span>
            <strong>{status?.neo4j_status ?? '—'}</strong>
          </div>
          <div className="module-header__metric">
            <span>Survey API</span>
            <strong>{status?.deliberation_status ?? '—'}</strong>
          </div>
          <div className="module-header__metric">
            <span>Slack</span>
            <strong>{status?.slack_configured ? 'On' : 'Off'}</strong>
          </div>
        </div>
      </header>

      {error ? <div className="module-alert">{error}</div> : null}

      <div className="subtabs">
        {[
          { id: 'admin', label: translate('settings.tabs.admin') },
          { id: 'data', label: translate('settings.tabs.data') },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={tab.id === activeTab ? 'subtab active' : 'subtab'}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'admin' && (
        <div className="stack">
          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Settings overview</h3>
                <p className="muted">Monitor system health and manage admin tools.</p>
              </div>
              <div className="pill">Admin</div>
            </div>
          </div>
          <div className="module-grid">
            <div className="module-card">
            <h3>System status</h3>
            <p className="muted">Live connectivity + config.</p>
            <div className="metric-row">
              <span>Neo4j</span>
              <strong>{status?.neo4j_status ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Survey API</span>
              <strong>{status?.deliberation_status ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Slack</span>
              <strong>{status?.slack_configured ? 'Configured' : 'Not set'}</strong>
            </div>
            <div className="metric-row">
              <span>WhatsApp</span>
              <strong>{status?.whatsapp_configured ? 'Configured' : 'Not set'}</strong>
            </div>
          <div className="metric-row">
            <span>Feedback email</span>
            <strong>{status?.feedback_configured ? 'Configured' : 'Not set'}</strong>
          </div>
          </div>

          <div className="module-card">
            <h3>Slack test</h3>
            {slackError ? <div className="module-alert">{slackError}</div> : null}
            <textarea
              className="textarea"
              value={slackMessage}
              onChange={(event) => setSlackMessage(event.target.value)}
            />
            <button className="button" type="button" onClick={handleSlackTest}>
              Send test message
            </button>
          </div>

          <div className="module-card module-card__wide">
            <h3>Clear Aura DB</h3>
            <p className="muted">
              Danger zone: deletes all nodes and relationships in Aura DB.
            </p>
            {clearError ? <div className="module-alert">{clearError}</div> : null}
            {clearStatus ? (
              <div className="module-alert module-alert--success">{clearStatus}</div>
            ) : null}
            <div className="filter-row">
              <input
                className="input"
                placeholder="Type CLEAR AURA DB to confirm"
                value={clearConfirm}
                onChange={(event) => setClearConfirm(event.target.value)}
              />
              <button
                className="button"
                type="button"
                onClick={handleClearDb}
                disabled={clearLoading}
              >
                {clearLoading ? 'Clearing…' : 'Clear Aura DB'}
              </button>
            </div>
          </div>

          <div className="module-card module-card__wide">
            <h3>Feedback log</h3>
            <div className="table">
              <div className="table-row table-head">
                <span>Page</span>
                <span>Name</span>
                <span>Email</span>
                <span>Status</span>
              </div>
              {feedback.length === 0 && (
                <div className="table-row empty">No feedback entries.</div>
              )}
              {feedback.map((row) => (
                <div className="table-row" key={row.feedbackId}>
                  <span>{row.page}</span>
                  <span>{row.name}</span>
                  <span>{row.email}</span>
                  <span>{row.emailStatus}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="module-card module-card__wide">
            <h3>Delete records</h3>
            <p className="muted">Danger zone: deletions are permanent.</p>
            <div className="table">
              <div className="table-row table-head">
                <span>Type</span>
                <span>Label</span>
                <span />
              </div>
              {deleteData.tasks.map((task) => (
                <div className="table-row" key={task.taskId}>
                  <span>Task</span>
                  <span>{task.title}</span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete('task', task.taskId)}
                  >
                    Delete
                  </button>
                </div>
              ))}
              {deleteData.events.map((event) => (
                <div className="table-row" key={event.eventId}>
                  <span>Event</span>
                  <span>{event.name}</span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete('event', event.eventId)}
                  >
                    Delete
                  </button>
                </div>
              ))}
              {deleteData.segments.map((segment) => (
                <div className="table-row" key={segment.segmentId}>
                  <span>Segment</span>
                  <span>{segment.name}</span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete('segment', segment.segmentId)}
                  >
                    Delete
                  </button>
                </div>
              ))}
              {deleteData.groups.map((group) => (
                <div className="table-row" key={group.groupId}>
                  <span>WhatsApp</span>
                  <span>{group.name}</span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete('group', group.groupId)}
                  >
                    Delete
                  </button>
                </div>
              ))}
              {deleteData.conversations.map((convo) => (
                <div className="table-row" key={convo.id}>
                  <span>Conversation</span>
                  <span>{convo.topic}</span>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => handleDelete('conversation', convo.id)}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>
          </div>
        </div>
      )}

      {activeTab === 'data' && (
        <div className="stack">
          <div className="module-card module-card__wide section-intro">
            <div className="card-header">
              <div>
                <h3>Data management</h3>
                <p className="muted">Export summaries and monitor data quality.</p>
              </div>
              <div className="pill">Data</div>
            </div>
          </div>
          <div className="module-grid">
            <div className="module-card">
            <h3>People data quality</h3>
            <div className="metric-row">
              <span>Total people</span>
              <strong>{summary?.total_people ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Missing gender</span>
              <strong>{summary?.missing_gender ?? '—'}</strong>
            </div>
            <div className="metric-row">
              <span>Missing age</span>
              <strong>{summary?.missing_age ?? '—'}</strong>
            </div>
            <button className="button-secondary" type="button" onClick={handleExportSummary}>
              Export people summary
            </button>
          </div>
          </div>
        </div>
      )}

      <div className="module-footer">
        <span>Backend scope:</span>
        <strong>Survey API + /crm routes (Network)</strong>
      </div>
    </section>
  )
}
