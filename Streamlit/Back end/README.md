## Streamlit Back end

Run:
```
python -m uvicorn app:app --host 0.0.0.0 --port 8011
```

Env:
- Uses `.env` in this folder.
# Streamlit backend shell

This folder provides a FastAPI entrypoint wrapper for the deliberation API.

Run locally (from this folder):
- `python -m uvicorn app:app --reload --host 0.0.0.0 --port 8010`
