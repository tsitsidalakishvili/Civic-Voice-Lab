## React Back end

Run:
```
python -m uvicorn app:app --host 0.0.0.0 --port 8011
```

Env:
- Uses `.env` in this folder.

### Render deployment
Service settings:
- Root directory: `React/Back end`
- Build command: `pip install -r requirements.txt`
- Start command: `python -m uvicorn app:app --host 0.0.0.0 --port $PORT`

Environment variables (Render dashboard):
- `DELIBERATION_NEO4J_URI`
- `DELIBERATION_NEO4J_USER` (or `DELIBERATION_NEO4J_USERNAME`)
- `DELIBERATION_NEO4J_PASSWORD`
- `DELIBERATION_NEO4J_DATABASE`
- `CORS_ORIGINS` (set to your Vercel URL)
# React backend shell

This folder wraps the existing deliberation FastAPI service so the React UI
can run against the same backend.

Run locally (from this folder):
- `python -m uvicorn app:app --reload --host 0.0.0.0 --port 8010`
