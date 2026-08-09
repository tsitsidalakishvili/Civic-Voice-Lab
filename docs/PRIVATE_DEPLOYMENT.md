# Private deployment baseline

Keep both services suspended until every verification item below passes.

## Render backend

Set these server-side environment variables:

```text
FS_AUTH_ENABLED=1
FS_AUTH_MODE=password
FS_ACCESS_USERS_FILE=/etc/secrets/access_users.json
FS_SESSION_SECRET=<at least 32 cryptographically random bytes>
FS_COMPLIANCE_HASH_KEY=<a different random secret>
FS_FRONTEND_ORIGIN=https://fs-frontend-puce.vercel.app
CORS_ORIGINS=https://fs-frontend-puce.vercel.app
FS_AUTH_PUBLIC_RULES=
```

Create `access_users.json` as a Render Secret File. Its contents use exact emails and password hashes only. Generate or update the file locally with:

```powershell
python "React\Back end\tools\manage_access_users.py" add person@example.org
```

The command asks for the password twice without displaying it. Upload the resulting ignored `React/Back end/access_users.local.json` as the Render Secret File. Never commit or send this file through chat or email.

An empty `FS_AUTH_PUBLIC_RULES` uses the private defaults: only health checks and authentication status are public. Any future public form must be enabled route-by-route after privacy, consent, minimisation, rate-limiting, and abuse controls are reviewed.

## Vercel frontend

Set:

```text
VITE_API_BASE_URL=https://<your-render-service>
VITE_AUTH_ENABLED=true
VITE_AUTH_MODE=password
```

Do **not** define passwords, password hashes, the access-user file, or session secrets in Vercel. Vite variables are shipped to every visitor. Authentication uses the backend and an HttpOnly session cookie.

## Verification before resuming

1. Open the frontend in a private/incognito window. It must show only the private access screen.
2. A wrong key must fail without displaying modules or records.
3. With no `Authorization` header, `/crm/dashboard`, `/crm/people`, `/due-diligence/*`, `/docs`, and `/openapi.json` must return `401`.
4. A listed email with the correct password must create a Secure, HttpOnly session cookie. Unlisted emails and wrong passwords must receive the same generic error.
5. The backend must allow CORS only from the exact production frontend origin.
6. Search the built frontend and deployment variables to confirm the bearer token is absent.
7. Confirm no real personal records are present in Git, frontend assets, browser analytics, logs, screenshots, or demo fixtures.
8. Enable Render first, complete API checks, then deploy Vercel and repeat the incognito test before sharing the URL.

This exact-email password file is intended for a very small team. If the user count or risk grows, replace it with organization OIDC and MFA.
