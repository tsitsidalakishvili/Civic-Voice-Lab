# Civic Voice Lab Platform

Civic Voice Lab is a modular civic-operations platform for relationship management, campaigns, deliberation, due diligence, and connected-data analysis. The production application is a React/Vite single-page app backed by FastAPI and Neo4j.

## Start here

- [Documentation index](docs/README.md)
- [Platform overview](docs/PLATFORM_OVERVIEW.md)
- [Local setup and configuration](docs/GETTING_STARTED.md)
- [Architecture and data](docs/ARCHITECTURE.md)
- [API guide](docs/API_GUIDE.md)
- [Deployment and operations](docs/OPERATIONS.md)
- [Security, privacy, and responsible use](docs/SECURITY_PRIVACY.md)
- [Testing and contribution](docs/CONTRIBUTING.md)

## Quick start

```powershell
cd "React/Back end"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FS_AUTH_ENABLED="0" # local development only
python -m uvicorn app:app --reload --host 127.0.0.1 --port 8010
```

In a second terminal:

```powershell
cd "React/Front end"
npm ci
npm run dev
```

Open `http://localhost:5173`. The API health endpoint is `http://localhost:8010/healthz`, and interactive OpenAPI documentation is at `http://localhost:8010/docs`.

> Never disable authentication in a shared or production environment. See the security guide before loading personal, political, financial, or investigative data.

