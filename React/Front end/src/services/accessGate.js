const ACCESS_EMAIL_STORAGE_KEY = 'fs_access_email'

export function getStoredAccessEmail() {
  if (typeof window === 'undefined') return ''
  return String(window.localStorage.getItem(ACCESS_EMAIL_STORAGE_KEY) || '').trim()
}

export function saveStoredAccessEmail(email) {
  if (typeof window === 'undefined') return
  const value = String(email || '').trim()
  if (value) window.localStorage.setItem(ACCESS_EMAIL_STORAGE_KEY, value)
  else window.localStorage.removeItem(ACCESS_EMAIL_STORAGE_KEY)
}

export function clearStoredAccessEmail() {
  saveStoredAccessEmail('')
}
