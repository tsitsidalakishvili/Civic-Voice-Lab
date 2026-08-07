import { beginOrganizationLogin } from '../services/sessionAuth'

export function PlatformAccessGate({ state = 'unauthenticated', message = '', onRetry }) {
  const unauthorized = state === 'unauthorized'
  const unavailable = state === 'unavailable'
  const expired = state === 'expired' || state === 'revoked'

  return (
    <main className="access-gate" aria-labelledby="access-title">
      <section className="access-gate__card">
        <p className="eyebrow">Freedom Square staff workspace</p>
        <h1 id="access-title">
          {unauthorized ? 'Access is not authorized' : unavailable ? 'Sign-in service unavailable' : 'Organization sign-in'}
        </h1>
        <p className="muted">
          {unauthorized
            ? 'You are signed in, but your organization account does not have access to this workspace.'
            : expired
              ? 'Your session ended or was revoked. Sign in again to continue securely.'
              : unavailable
                ? 'The private workspace remains locked while authentication is unavailable.'
                : 'Use your approved organization account. This application never asks for or stores your organization password.'}
        </p>
        {message ? <div className="module-alert" role="alert">{message}</div> : null}
        {!unauthorized && !unavailable ? (
          <button className="button" type="button" onClick={() => beginOrganizationLogin()}>
            Sign in with organization account
          </button>
        ) : null}
        {onRetry ? <button className="button button--secondary" type="button" onClick={onRetry}>Try again</button> : null}
        {unauthorized ? <p className="muted">Contact an administrator through your normal internal support channel.</p> : null}
      </section>
    </main>
  )
}
