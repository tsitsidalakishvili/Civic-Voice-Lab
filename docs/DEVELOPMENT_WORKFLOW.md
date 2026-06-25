# Development Workflow

Use this workflow so new features land cleanly and deployments are predictable.

## Branches

- `main` is the deployable branch. Keep it stable.
- Create a feature branch before new work: `codex/<short-feature-name>` or `feature/<short-feature-name>`.
- Use small branches for one product change at a time, for example `codex/data-hub-graph-fullscreen`.
- Merge feature branches into `main` only after build/tests pass.

## Local Development

Frontend:

```powershell
cd "React/Front end"
npm install
npm run dev
npm run build
```

Backend:

```powershell
cd "React/Back end"
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8010
```

## Before Pushing

Run the checks that match the touched area:

```powershell
cd "React/Front end"
npm run build
npm run test
```

If backend code changed, start the backend locally and verify the affected endpoint. Add backend tests as the API surface becomes more stable.

## Commit Scope

- Stage source files deliberately, not generated files.
- Do not commit `dist/`, `node_modules/`, `.venv/`, logs, runtime caches, or `outputs/`.
- Keep feature work separate from cleanup work unless the cleanup is required for the feature.

## Deployments

Current hosting settings depend on the existing folder names:

- Frontend root: `React/Front end`
- Backend root: `React/Back end`

Do not rename those root folders without also updating Vercel/Render project settings and verifying deployment.
