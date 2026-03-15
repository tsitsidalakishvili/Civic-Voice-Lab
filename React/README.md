## React (production)

Use this folder for the production UI and backend.

### Run (frontend)
```
cd "Front end"
npm install
npm run dev
```

### Run (backend)
```
cd "Back end"
python -m uvicorn app:app --host 0.0.0.0 --port 8011
```

### Env files
- `Front end/.env` for local dev
- `Front end/.env.production` for deployed API base
