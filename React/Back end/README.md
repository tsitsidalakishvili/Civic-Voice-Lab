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

### Local sentiment analysis

Statement-comment sentiment uses a local Hugging Face transformer by default, so there is no per-comment AI API cost. The engine normalizes text, keeps the original context for the model, stores label, score, confidence, provider, and processed text, and falls back safely if the model cannot load.

Recommended Render environment variables:
- `SENTIMENT_PROVIDER=transformer`
- `SENTIMENT_TRANSFORMER_MODEL=cardiffnlp/twitter-xlm-roberta-base-sentiment`
- `SENTIMENT_TRANSFORMER_LOCAL_FILES_ONLY=0`

Render will download the model on first load unless it is already cached. Use a Render instance with enough memory for `torch` + XLM-R sentiment, ideally at least 1-2 GB RAM.

Optional paid AI fallback, only if you want it later:
- `SENTIMENT_PROVIDER=auto`
- `SENTIMENT_LLM_API_URL=https://api.openai.com/v1/chat/completions` or another OpenAI-compatible chat-completions URL
- `SENTIMENT_LLM_API_KEY=<your API key>`
- `SENTIMENT_LLM_MODEL=gpt-4.1-mini` or another compatible model

Existing comments can be recalculated from `React/Back end/deliberation/api`:
```
python -m app.scripts.backfill_statement_sentiment
python -m app.scripts.backfill_statement_sentiment --apply
```

If no local model or AI provider is available, the engine returns neutral/unavailable and the backfill skips updates by default.
