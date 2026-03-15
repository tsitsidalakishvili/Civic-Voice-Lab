## Streamlit Front end

Run:
```
streamlit run "Home.py"
```

Env:
- `DELIBERATION_API_URL` points to the backend.
- `STREAMLIT_MOCK_DATA=true` disables Neo4j access for safe experiments.

Env files:
- `.env` (current local settings)
- `.env.experiment` (mock data)
- `.env.production` (production API base)
# Streamlit frontend shell

This folder mirrors the Streamlit UI entrypoint and pages. Files here proxy
to the canonical app files in the repo root to avoid duplication.

Run locally:
- `streamlit run Home.py`
