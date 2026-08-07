// Migration compatibility only. Normal authentication uses an HttpOnly cookie.
export const getAuthSnapshot = () => ({ enabled: true, mode: 'session' })
export const getAuthHeaders = () => ({})

export function saveAuthCredentials() {
  throw new Error('Use organization sign-in; browser-managed credentials are disabled.')
}

export function clearAuthCredentials() {
  if (typeof window === 'undefined') return
  for (const storage of [window.localStorage, window.sessionStorage]) {
    storage.removeItem('fs_auth_token')
    storage.removeItem('fs_auth_api_key')
    storage.removeItem('fs_access_email')
  }
}
