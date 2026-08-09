import React, { useEffect, useState } from 'react'
import { fetchAuthCapabilities, loginWithCredentials, organizationLoginUrl } from '../services/sessionAuth'

export function PlatformAccessGate({ state = 'unauthenticated', message = '', onRetry, onAuthenticated }) {
  const unauthorized = state === 'unauthorized'
  const unavailable = state === 'unavailable'
  const expired = state === 'expired' || state === 'revoked'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loginError, setLoginError] = useState('')
  const [capabilities, setCapabilities] = useState(null)
  const [capabilitiesError, setCapabilitiesError] = useState('')

  useEffect(() => {
    let mounted = true
    fetchAuthCapabilities()
      .then((result) => { if (mounted) setCapabilities(result) })
      .catch(() => { if (mounted) setCapabilitiesError('The sign-in service could not be reached.') })
    return () => { mounted = false }
  }, [])

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setLoginError('')
    try {
      await loginWithCredentials(username, password)
      setPassword('')
      onAuthenticated?.()
    } catch (error) {
      setPassword('')
      setLoginError(error?.message || 'Sign-in failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const blocked = unauthorized || unavailable
  const showPassword = !blocked && capabilities?.passwordLogin === true
  const showOrganization = !blocked && capabilities?.organizationLogin === true
  const noMethod = !blocked && capabilities !== null && !showPassword && !showOrganization

  const prompt = () => {
    if (unauthorized) return 'You are signed in, but your organization account does not have access to this workspace.'
    if (expired) return 'Your session ended or was revoked. Sign in again to continue securely.'
    if (unavailable) return 'The private workspace remains locked while authentication is unavailable.'
    if (showPassword) return 'Enter your approved email and password. The password is sent only to the secured backend and is never stored in this browser.'
    if (showOrganization) return 'Sign in with your organization account to continue.'
    return 'Checking which sign-in methods this server supports…'
  }

  return (
    <main className="access-gate" aria-labelledby="access-title">
      <section className="access-gate__card">
        <p className="eyebrow">Freedom Square staff workspace</p>
        <h1 id="access-title">
          {unauthorized ? 'Access is not authorized' : unavailable ? 'Sign-in service unavailable' : 'Staff sign-in'}
        </h1>
        <p className="muted">{prompt()}</p>
        {message ? <div className="module-alert" role="alert">{message}</div> : null}
        {capabilitiesError ? <div className="module-alert" role="alert">{capabilitiesError}</div> : null}
        {noMethod ? (
          <div className="module-alert" role="alert">
            This server has no sign-in method configured. Check FS_AUTH_MODE on the backend.
          </div>
        ) : null}
        {loginError ? <div className="module-alert" role="alert">{loginError}</div> : null}
        {showOrganization ? (
          <a className="button" href={organizationLoginUrl(`${window.location.pathname}${window.location.search}`)}>
            Sign in with your organization account
          </a>
        ) : null}
        {showPassword ? (
          <form className="access-gate__form" onSubmit={submit}>
            <label>
              {import.meta.env.DEV ? 'Email or local username' : 'Email'}
              <input
                required
                type={import.meta.env.DEV ? 'text' : 'email'}
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label>Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <button className="button" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
          </form>
        ) : null}
        {onRetry ? <button className="button button--secondary" type="button" onClick={onRetry}>Try again</button> : null}
        {unauthorized ? <p className="muted">Contact an administrator through your normal internal support channel.</p> : null}
      </section>
    </main>
  )
}
