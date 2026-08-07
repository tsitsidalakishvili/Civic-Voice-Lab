// Migration compatibility only. Normal authentication uses an HttpOnly cookie.
export const getAuthSnapshot = () => ({ enabled: true, mode: 'session' })
export const getAuthHeaders = () => ({})

export function saveAuthCredentials() {
  throw new Error('Use organization sign-in; browser-managed credentials are disabled.')
}

export function clearAuthCredentials() {
  // Session cookies are HttpOnly and revoked by the backend logout endpoint.
  // No authentication material is readable or removable by client JavaScript.
}
