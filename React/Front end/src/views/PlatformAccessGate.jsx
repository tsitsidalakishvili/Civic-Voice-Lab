import { useState } from 'react'
import { loginWithCredentials } from '../services/sessionAuth'

export function PlatformAccessGate({ state = 'unauthenticated', message = '', onRetry, onAuthenticated }) {
  const unauthorized = state === 'unauthorized'
  const unavailable = state === 'unavailable'
  const expired = state === 'expired' || state === 'revoked'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loginError, setLoginError] = useState('')

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

  return (
    <main className="access-gate" aria-labelledby="access-title">
      <section className="access-gate__card">
        <p className="eyebrow">Freedom Square staff workspace</p>
        <h1 id="access-title">
          {unauthorized ? 'Access is not authorized' : unavailable ? 'Sign-in service unavailable' : 'Staff sign-in'}
        </h1>
        <p className="muted">
          {unauthorized
            ? 'You are signed in, but your organization account does not have access to this workspace.'
            : expired
              ? 'Your session ended or was revoked. Sign in again to continue securely.'
              : unavailable
                ? 'The private workspace remains locked while authentication is unavailable.'
                : 'Enter the temporary staff credential. The password is sent only to the secured backend and is never stored in this browser.'}
        </p>
        {message ? <div className="module-alert" role="alert">{message}</div> : null}
        {loginError ? <div className="module-alert" role="alert">{loginError}</div> : null}
        {!unauthorized && !unavailable ? (
          <form className="access-gate__form" onSubmit={submit}>
            <label>Username<input required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
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
