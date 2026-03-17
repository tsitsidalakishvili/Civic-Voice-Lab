const DEFAULT_API_BASE = 'http://localhost:8010'

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE

export async function getJson(path) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const response = await fetch(url)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json()
}

export async function requestJson(path, { method = 'POST', payload, headers } = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const response = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(headers || {}),
    },
    body: payload === undefined ? null : JSON.stringify(payload),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  if (response.status === 204) {
    return null
  }
  return response.json()
}

export async function requestForm(path, { method = 'POST', formData } = {}) {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const response = await fetch(url, {
    method,
    body: formData,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  if (response.status === 204) {
    return null
  }
  return response.json()
}
