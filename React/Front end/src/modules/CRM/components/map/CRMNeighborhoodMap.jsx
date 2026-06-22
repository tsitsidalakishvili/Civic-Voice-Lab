import { useEffect, useMemo, useState } from 'react'
import { IconMaximize, IconMinimize } from '@tabler/icons-react'
import { CircleMarker, MapContainer, TileLayer, Tooltip as LeafletTooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { getJson } from '../../../../services/api'

const TBILISI_CENTER = [41.7151, 44.8271]
const GEORGIA_CENTER = [42.05, 43.65]
const TBILISI_BOUNDS = [
  [41.55, 44.6],
  [41.9, 45.05],
]
const GEORGIA_BOUNDS = [
  [41.0, 40.0],
  [43.8, 46.8],
]

const defaultFilters = {
  supporterType: '',
  skill: '',
  tag: '',
  gender: '',
  ageGroup: '',
}

function buildQuery(filters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value)
  })
  const query = params.toString()
  return query ? `?${query}` : ''
}

function bubbleRadius(total) {
  return Math.max(3, Math.min(12, Math.sqrt(Number(total) || 0) * 1.1))
}


function markerColor(row) {
  if (row.members > row.supporters) return '#f97316'
  if (row.partners > 0 && row.partners >= row.supporters) return '#2563eb'
  return '#7c3aed'
}

function MapViewport({ bounds, trigger }) {
  const map = useMap()

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      map.invalidateSize()
      map.fitBounds(bounds, { padding: [24, 24] })
    }, 180)
    return () => window.clearTimeout(timeout)
  }, [bounds, map, trigger])

  return null
}

function NeighborhoodPeoplePanel({ neighborhood, people, loading, error, onClose }) {
  const title = neighborhood ? `People in ${neighborhood.microArea}` : 'People on map'
  const subtitle = neighborhood
    ? `${neighborhood.total} people aggregated at neighborhood precision.`
    : `${people.length} mapped people match the current filters.`

  return (
    <aside className="neighborhood-panel">
      <div className="neighborhood-panel__header">
        <div>
          <h3>{title}</h3>
          <p className="muted">{subtitle}</p>
        </div>
        {neighborhood ? (
          <button className="button-secondary" type="button" onClick={onClose}>
            Show all
          </button>
        ) : null}
      </div>
      {loading ? <p className="muted">Loading people...</p> : null}
      {error ? <div className="module-alert">{error}</div> : null}
      {!loading && !error ? (
        <div className="table table--scroll neighborhood-panel__table">
          <div className="table-row table-row--map table-head">
            <span>Name</span>
            <span>Type</span>
            <span>Status</span>
            <span>Contact</span>
            <span>Neighborhood</span>
          </div>
          {people.map((person) => (
            <div className="table-row table-row--map" key={person.personId || person.email}>
              <span>{person.fullName}</span>
              <span>{person.type}</span>
              <span>{person.status}</span>
              <span>{person.email || person.phone || 'Restricted'}</span>
              <span>{person.neighborhood || person.microArea || '-'}</span>
            </div>
          ))}
          {people.length === 0 ? <p className="muted">No people match these filters.</p> : null}
        </div>
      ) : null}
    </aside>
  )
}

export default function CRMNeighborhoodMap() {
  const [neighborhoods, setNeighborhoods] = useState([])
  const [unmatched, setUnmatched] = useState([])
  const [allPeople, setAllPeople] = useState([])
  const [selected, setSelected] = useState(null)
  const [selectedPeople, setSelectedPeople] = useState([])
  const [loading, setLoading] = useState(false)
  const [peopleLoading, setPeopleLoading] = useState(false)
  const [error, setError] = useState('')
  const [peopleError, setPeopleError] = useState('')
  const [filters, setFilters] = useState(defaultFilters)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [mapExpanded, setMapExpanded] = useState(false)

  const query = useMemo(() => buildQuery(filters), [filters])

  useEffect(() => {
    setLoading(true)
    setError('')
    Promise.all([
      getJson(`/crm/map/neighborhoods${query}`, { forceRefresh: true }),
      getJson(`/crm/map/people${query}`, { forceRefresh: true }),
      getJson('/crm/locations/unmatched', { forceRefresh: true }),
    ])
      .then(([mapPayload, peoplePayload, unmatchedPayload]) => {
        setNeighborhoods(Array.isArray(mapPayload) ? mapPayload : [])
        setAllPeople(Array.isArray(peoplePayload) ? peoplePayload : [])
        setUnmatched(Array.isArray(unmatchedPayload) ? unmatchedPayload : [])
      })
      .catch((err) => setError(err.message || 'Unable to load neighborhood map.'))
      .finally(() => setLoading(false))
  }, [query])

  useEffect(() => {
    if (!selected) {
      setSelectedPeople([])
      return
    }
    setPeopleLoading(true)
    setPeopleError('')
    getJson(`/crm/map/neighborhoods/${encodeURIComponent(selected.id)}/people${query}`, {
      forceRefresh: true,
    })
      .then((payload) => setSelectedPeople(Array.isArray(payload) ? payload : []))
      .catch((err) => setPeopleError(err.message || 'Unable to load neighborhood people.'))
      .finally(() => setPeopleLoading(false))
  }, [selected, query])

  const hasGeorgiaScope = neighborhoods.some((row) => row.city && row.city !== 'Tbilisi')
  const mapCenter = hasGeorgiaScope ? GEORGIA_CENTER : TBILISI_CENTER
  const mapBounds = hasGeorgiaScope ? GEORGIA_BOUNDS : TBILISI_BOUNDS
  const mapZoom = hasGeorgiaScope ? 7 : 12

  const totalPeople = neighborhoods.reduce((sum, row) => sum + Number(row.total || 0), 0)

  useEffect(() => {
    document.body.classList.toggle('crm-map-is-expanded', mapExpanded)
    return () => document.body.classList.remove('crm-map-is-expanded')
  }, [mapExpanded])

  return (
    <div className="crm-neighborhood-map">
      <div className={`module-card module-card__wide panel panel--highlight map-card ${mapExpanded ? 'map-card--expanded' : ''}`}>
        <div className="card-header">
          <div>
            <h3>Map</h3>
            <p className="muted">
              {totalPeople} people shown in {neighborhoods.length} map bubbles.
            </p>
          </div>
          <div className="map-legend">
            <span><span className="legend-dot legend-dot--supporter" /> Supporters</span>
            <span><span className="legend-dot legend-dot--member" /> Members</span>
          </div>
        </div>

        <div className="map-filters">
          <div className="map-filters__actions">
            <button
              className="map-filters__toggle map-filters__icon-toggle"
              type="button"
              onClick={() => setMapExpanded((prev) => !prev)}
              aria-pressed={mapExpanded}
              aria-label={mapExpanded ? 'Exit expanded map' : 'Expand map'}
              title={mapExpanded ? 'Exit expanded map' : 'Expand map'}
            >
              {mapExpanded ? <IconMinimize size={17} /> : <IconMaximize size={17} />}
            </button>
            <button
              className="map-filters__toggle"
              type="button"
              onClick={() => setFiltersOpen((prev) => !prev)}
              aria-expanded={filtersOpen}
            >
              {filtersOpen ? 'Close filters' : 'Filters'}
            </button>
          </div>
          {unmatched.length ? (
            <span className="location-review-pill">
              {unmatched.length} unmatched locations need review
            </span>
          ) : null}
          {filtersOpen ? (
            <div className="map-filters__panel">
              <div className="map-filters__header">
                <h4>Map filters</h4>
                <p className="muted">Filter aggregated neighborhoods without exposing exact pins.</p>
              </div>
              <div className="map-filters__body">
                <label className="label">
                  Audience
                  <select
                    className="select select--compact"
                    value={filters.supporterType}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, supporterType: event.target.value }))
                    }
                  >
                    <option value="">All people</option>
                    <option value="Supporter">Supporters</option>
                    <option value="Member">Members</option>
                    <option value="Partner">Partners</option>
                  </select>
                </label>
                <label className="label">
                  Gender
                  <select
                    className="select select--compact"
                    value={filters.gender}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, gender: event.target.value }))
                    }
                  >
                    <option value="">All genders</option>
                    <option value="F">Female</option>
                    <option value="M">Male</option>
                    <option value="O">Other</option>
                    <option value="Unspecified">Unspecified</option>
                  </select>
                </label>
                <label className="label">
                  Age group
                  <select
                    className="select select--compact"
                    value={filters.ageGroup}
                    onChange={(event) =>
                      setFilters((prev) => ({ ...prev, ageGroup: event.target.value }))
                    }
                  >
                    <option value="">All ages</option>
                    <option value="18-24">18-24</option>
                    <option value="25-34">25-34</option>
                    <option value="35-44">35-44</option>
                    <option value="45-54">45-54</option>
                    <option value="55-64">55-64</option>
                    <option value="65+">65+</option>
                  </select>
                </label>
                <label className="label">
                  Skill contains
                  <input
                    className="input input--compact"
                    value={filters.skill}
                    onChange={(event) => setFilters((prev) => ({ ...prev, skill: event.target.value }))}
                  />
                </label>
                <button className="button-secondary" type="button" onClick={() => setFilters(defaultFilters)}>
                  Reset filters
                </button>
              </div>
            </div>
          ) : null}
        </div>

        {loading ? <p className="muted">Loading neighborhood map...</p> : null}
        {error ? <div className="module-alert">{error}</div> : null}
        {!loading && !error && neighborhoods.length === 0 ? (
          <p className="muted">No matched neighborhoods for the selected filters.</p>
        ) : null}
        {!loading && !error && neighborhoods.length > 0 ? (
          <MapContainer center={mapCenter} zoom={mapZoom} maxBounds={mapBounds} className="map-canvas">
            <MapViewport bounds={mapBounds} trigger={mapExpanded} />
            <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {neighborhoods.map((row) => {
              const color = markerColor(row)
              return (
                <CircleMarker
                  key={row.id}
                  center={[row.lat, row.lng]}
                  radius={bubbleRadius(row.total)}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.68, opacity: 0.92, weight: 1 }}
                  eventHandlers={{ click: () => setSelected(row) }}
                >
                  <LeafletTooltip direction="top" className="map-count-tooltip">
                    {row.microArea}: {row.total} people
                  </LeafletTooltip>

                </CircleMarker>
              )
            })}
          </MapContainer>
        ) : null}
      </div>

      <NeighborhoodPeoplePanel
        neighborhood={selected}
        people={selected ? selectedPeople : allPeople}
        loading={selected ? peopleLoading : loading}
        error={selected ? peopleError : error}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}

