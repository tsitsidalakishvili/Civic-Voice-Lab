import { useState } from 'react'
import { requestJson } from '../services/api'
import { saveStoredAccessEmail } from '../services/accessGate'

export function PlatformAccessGate({ onGranted }) {
  const [email, setEmail] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    const candidate = email.trim().toLowerCase()
    if (!candidate) {
      setError('Enter your email address to continue.')
      return
    }
    setChecking(true)
    setError('')
    try {
      const result = await requestJson('/platform/access/verify', {
        payload: { email: candidate },
      })
      if (result?.allowed) {
        saveStoredAccessEmail(candidate)
        if (onGranted) onGranted(candidate)
      } else {
        setError('This email does not have access to the platform.')
      }
    } catch (err) {
      setError(err?.message || 'Unable to verify access. Try again.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="access-gate">
      <form className="access-gate__card" onSubmit={handleSubmit}>
        <h2>Freedom Square</h2>
        <p className="muted">
          This platform is restricted. Enter your email address to continue.
        </p>
        <input
          className="input"
          type="email"
          autoFocus
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
        {error ? <div className="module-alert">{error}</div> : null}
        <button className="button" type="submit" disabled={checking}>
          {checking ? 'Checking...' : 'Continue'}
        </button>
      </form>
    </div>
  )
}
