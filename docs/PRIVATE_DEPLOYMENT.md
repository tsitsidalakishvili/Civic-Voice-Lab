# Private deployment baseline

Keep both services suspended until every verification item below passes.

## Render backend

Set these server-side environment variables:

```text
FS_AUTH_ENABLED=1
FS_AUTH_MODE=bearer
FS_AUTH_TOKEN=<at least 32 cryptographically random bytes>
CORS_ORIGINS=https://fs-frontend-puce.vercel.app
FS_AUTH_PUBLIC_RULES=
```

Generate the token with a password manager or `python -c "import secrets; print(secrets.token_urlsafe(48))"` on a trusted machine. Store it only in Render and provide it to authorised staff through a secure channel. Do not use `VITE_AUTH_TOKEN`, `AUTH_TOKEN` in `runtime-config.js`, Git, chat, screenshots, or documentation.

An empty `FS_AUTH_PUBLIC_RULES` uses the private defaults: only health checks and authentication status are public. Any future public form must be enabled route-by-route after privacy, consent, minimisation, rate-limiting, and abuse controls are reviewed.

## Vercel frontend

Set:

```text
VITE_API_BASE_URL=https://<your-render-service>
VITE_AUTH_ENABLED=true
VITE_AUTH_MODE=bearer
```

Do **not** define `VITE_AUTH_TOKEN` or `VITE_AUTH_API_KEY`; Vite variables are shipped to every visitor. Staff enter the private key at runtime. It is retained only in browser session storage and disappears when the browser session ends.

## Verification before resuming

1. Open the frontend in a private/incognito window. It must show only the private access screen.
2. A wrong key must fail without displaying modules or records.
3. With no `Authorization` header, `/crm/dashboard`, `/crm/people`, `/due-diligence/*`, `/docs`, and `/openapi.json` must return `401`.
4. With the correct bearer token, `/platform/auth/verify` must return `authenticated: true`.
5. The backend must allow CORS only from the exact production frontend origin.
6. Search the built frontend and deployment variables to confirm the bearer token is absent.
7. Confirm no real personal records are present in Git, frontend assets, browser analytics, logs, screenshots, or demo fixtures.
8. Enable Render first, complete API checks, then deploy Vercel and repeat the incognito test before sharing the URL.

This shared-token gate is an immediate containment baseline, not the final identity architecture. Replace it with per-user identity, MFA, RBAC, access revocation, and attributable audit logging before broader staff use.
