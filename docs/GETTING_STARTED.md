# Getting Started and Configuration

## Prerequisites

- Node.js compatible with Vite 8 and npm lockfile v3
- Python 3.10+ recommended
- Neo4j 5.x database reachable from the backend
- PowerShell examples below; equivalent shell commands are acceptable

## Local installation

Backend:

```powershell
cd "React/Back end"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.auth.example .env.auth
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8010
```

Frontend:

```powershell
cd "React/Front end"
npm ci
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8010` in `React/Front end/.env.development` when automatic local resolution is not appropriate. Do not put secrets in any `VITE_*` variable; Vite embeds these values in browser code.

## Required production settings

| Variable | Purpose |
| --- | --- |
| `DELIBERATION_NEO4J_URI` | Neo4j connection URI |
| `DELIBERATION_NEO4J_USER` or `DELIBERATION_NEO4J_USERNAME` | Database identity |
| `DELIBERATION_NEO4J_PASSWORD` | Database secret |
| `DELIBERATION_NEO4J_DATABASE` | Target database |
| `CORS_ORIGINS` | Exact comma-separated frontend origins |
| `FS_AUTH_ENABLED=1` | Enables API authentication; default is enabled |
| `FS_AUTH_MODE` | `bearer` or `api_key` |
| `FS_AUTH_TOKEN` or `FS_AUTH_API_KEY` | Matching server-side secret |
| `FS_AUTH_PUBLIC_RULES` | Explicit `METHOD:/path` public allowlist |
| `VITE_API_BASE_URL` | Public backend origin used at frontend build time |

Never deploy with authentication enabled but its selected secret empty. Use a secret manager, rotate secrets, and use distinct values per environment.

## Optional settings by capability

- Access gate: `FS_ALLOWED_EMAILS`.
- Translation: `FS_TRANSLATION_ENABLED`, `FS_TRANSLATION_WORKER_URL`, `FS_TRANSLATION_EN_KA_MODEL`, `FS_TRANSLATION_KA_EN_MODEL`, size limits.
- AI/data chat/sentiment/due diligence: `OPENAI_API_KEY` or capability-specific compatible URL/key/model settings. Send only data approved for that provider.
- Geocoding: `GOOGLE_MAPS_API_KEY`, geocoding strategy, location hint, timeout and per-request limit.
- Search/screening: OpenSanctions, Google Custom Search, declaration service, registry, Apify, and related capability-specific variables documented alongside their modules.
- Notifications: SMTP sender/recipient/host/user/password/TLS, Slack webhook, WhatsApp webhook and token.
- Public URLs/features: `FRONTEND_PUBLIC_URL`, `SUPPORTER_SIGNUP_BASE_URL`, `ENABLE_PUBLIC_CAMPAIGNS`, `ENABLE_PAYMENTS`, contribution limit.
- Privacy/exports/cache: `ANON_SALT`, survey minimum, export directory, CRM cache directory and expiry values.

Use `.env.auth.example` as a safe shape reference. Search the backend for `os.getenv` when enabling an optional connector; connector code remains the authoritative source until a typed settings registry replaces scattered environment access.

## Verify the installation

```powershell
Invoke-RestMethod http://localhost:8010/healthz
cd "React/Front end"
npm run build
npm run test -- --run
```

If authentication is enabled, call protected endpoints with `Authorization: Bearer <token>` or the configured API-key header. A healthy API returns `status: ok`; `degraded` means the server is up but Neo4j is unavailable or misconfigured.

## Common failures

- **Frontend “Failed to fetch”:** verify `VITE_API_BASE_URL`, backend availability, and exact `CORS_ORIGINS`.
- **401/403:** confirm auth mode, client header, secret, access gate, and public-rule syntax.
- **503 from API:** inspect `/healthz`; verify Neo4j URI, credentials, database, TLS/firewall, and Aura allowlists.
- **Connector unavailable:** check its capability endpoint where available and verify credentials, permission acknowledgement, egress, and kill switch.
- **Translation unavailable:** run the worker at the configured URL or disable translation explicitly.

