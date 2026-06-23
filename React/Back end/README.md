## React Back end

Run:
```
python -m uvicorn app:app --host 0.0.0.0 --port 8010
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
- `CORS_ORIGINS` (set to your Vercel URL, e.g. `https://fs-frontend-puce.vercel.app`)
# React backend shell

This folder wraps the existing deliberation FastAPI service so the React UI
can run against the same backend.

Run locally (from this folder):
- `python -m uvicorn app:app --reload --host 0.0.0.0 --port 8010`

### Sentiment analysis

Statement-comment sentiment uses an AI chat-completions API by default. The engine normalizes text, keeps the original context for the model, stores label, score, confidence, provider, and processed text, and falls back safely if the API is not configured.

Recommended Render environment variables:
- `SENTIMENT_PROVIDER=ai`
- `OPENAI_API_KEY=<your OpenAI API key>`
- `SENTIMENT_LLM_MODEL=gpt-4.1-mini`

Optional OpenAI-compatible configuration:
- `SENTIMENT_LLM_API_URL=https://api.openai.com/v1/chat/completions`
- `SENTIMENT_LLM_API_KEY=<your API key>`
- `SENTIMENT_LLM_TIMEOUT=20`

The diagnostic endpoint can be checked after deploy:
```
/sentiment/diagnostics?text=?? ??????????
```

Existing comments can be recalculated from `React/Back end/deliberation/api`:
```
python -m app.scripts.backfill_statement_sentiment
python -m app.scripts.backfill_statement_sentiment --apply
```

If no local model or AI provider is available, the engine returns neutral/unavailable and the backfill skips updates by default.
