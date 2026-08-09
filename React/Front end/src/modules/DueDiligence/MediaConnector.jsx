import { useEffect, useMemo, useState } from 'react'
import { IconAlertTriangle, IconExternalLink, IconNews, IconPlayerPlay, IconRefresh } from '@tabler/icons-react'
import { getJson, requestJson } from '../../services/api'

const pretty = (value) => String(value || '').replaceAll('-', ' ').replaceAll('_', ' ')

export function MediaConnector({ caseId, initialSubject = '', subjectType = 'Person', onImported }) {
  const [sources, setSources] = useState([])
  const [metaInfo, setMetaInfo] = useState(null)
  const [subject, setSubject] = useState(initialSubject)
  const [topics, setTopics] = useState('')
  const [maxResults, setMaxResults] = useState(12)
  const [selectedSources, setSelectedSources] = useState(['netgazeti', 'publika', 'interpressnews'])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!subject && initialSubject) setSubject(initialSubject)
  }, [initialSubject, subject])

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [sourceRows, meta] = await Promise.all([
        getJson('/due-diligence/media-sources', { forceRefresh: true }),
        getJson('/due-diligence/meta-content-library', { forceRefresh: true }),
      ])
      setSources(Array.isArray(sourceRows) ? sourceRows : [])
      setMetaInfo(meta || null)
    } catch (err) {
      setError(err.message || 'Unable to load media connectors.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const selectableSources = useMemo(
    () => sources.filter((source) => source.sourceId !== 'meta_content_library'),
    [sources],
  )
  const toggleSource = (sourceId) => setSelectedSources((current) =>
    current.includes(sourceId) ? current.filter((id) => id !== sourceId) : [...current, sourceId])

  const scan = async (event) => {
    event.preventDefault()
    if (!subject.trim()) { setError('Enter a person or organization to scan.'); return }
    if (!selectedSources.length) { setError('Select at least one media source.'); return }
    setScanning(true)
    setError('')
    setResult(null)
    try {
      const payload = await requestJson('/due-diligence/media-monitor', {
        method: 'POST',
        payload: {
          subject: subject.trim(),
          subjectType,
          caseId: caseId || undefined,
          topics: topics.split(',').map((item) => item.trim()).filter(Boolean),
          sourceIds: selectedSources,
          maxResults: Number(maxResults) || 12,
          persist: true,
        },
      })
      setResult(payload)
      onImported?.(payload)
    } catch (err) {
      setError(err.message || 'Media scan failed.')
    } finally {
      setScanning(false)
    }
  }

  return <div className="dd-connector-panel">
    <div className="dd-connector-panel__toolbar">
      <div><span className="dd-card-kicker">Georgian media</span><h4>Media monitoring</h4><p>Search approved publishers and preserve article-level evidence against this case.</p></div>
      <button className="button-secondary" type="button" onClick={load} disabled={loading}><IconRefresh size={14}/>{loading ? 'Checking…' : 'Refresh sources'}</button>
    </div>
    {error ? <div className="module-alert" role="alert">{error}</div> : null}
    <form className="dd-media-scan" onSubmit={scan}>
      <div className="dd-media-scan__fields">
        <label><span>Subject</span><input required value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Person or organization" /></label>
        <label><span>Topics <small>optional</small></span><input value={topics} onChange={(event) => setTopics(event.target.value)} placeholder="procurement, ownership" /></label>
        <label><span>Result limit</span><input type="number" min="1" max="50" value={maxResults} onChange={(event) => setMaxResults(event.target.value)} /></label>
      </div>
      <fieldset className="dd-media-sources"><legend>Publishers to search</legend>
        {selectableSources.length ? selectableSources.map((source) => <label key={source.sourceId} className={selectedSources.includes(source.sourceId) ? 'is-selected' : ''}><input type="checkbox" checked={selectedSources.includes(source.sourceId)} onChange={() => toggleSource(source.sourceId)} /><span><strong>{source.name}</strong><small>{pretty(source.status || source.accessModel || 'available')}</small></span></label>) : <p className="muted">No media publishers are currently available.</p>}
      </fieldset>
      <div className="dd-media-scan__action"><button className="button" type="submit" disabled={scanning || !selectableSources.length}><IconPlayerPlay size={15}/>{scanning ? 'Scanning publishers…' : 'Scan and preserve evidence'}</button><small>Results are evidence candidates, not automatic findings.</small></div>
    </form>
    {result ? <section className="dd-media-results"><div className="dd-media-results__summary"><IconNews size={18}/><strong>{result.mentions?.length || 0} mentions</strong><span>{result.storedCount || 0} preserved</span></div>{result.warnings?.map((warning) => <div className="module-alert" key={warning}><IconAlertTriangle size={14}/>{warning}</div>)}<div className="dd-media-results__list">{(result.mentions || []).map((mention) => <article key={mention.url}><div><strong>{mention.title}</strong><small>{mention.source} · {mention.publishedAt || 'Date not reported'}</small></div><a href={mention.url} target="_blank" rel="noreferrer" aria-label={`Open source article: ${mention.title}`}><IconExternalLink size={15}/></a></article>)}</div></section> : null}
    {metaInfo ? <details className="dd-connector-note"><summary>Meta Content Library access information</summary><p>{metaInfo.fitForDueDiligence}</p><p>{metaInfo.eligibleUsers}</p>{metaInfo.sourceUrl ? <a href={metaInfo.sourceUrl} target="_blank" rel="noreferrer">Open Meta documentation <IconExternalLink size={13}/></a> : null}</details> : null}
  </div>
}
