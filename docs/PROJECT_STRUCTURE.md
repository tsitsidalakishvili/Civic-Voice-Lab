# Project Structure

This repository keeps the deployed React/FastAPI product in `React/` and older reference applications in the legacy folders.

## Current Product

- `React/Front end/` - Vite React application.
- `React/Front end/src/app/` - application shell, routing between modules, and global app CSS.
- `React/Front end/src/modules/` - product modules. Each module owns its page, local components, tests, and module-specific helpers.
- `React/Front end/src/components/` - reusable cross-module UI behavior that is more specific than primitive UI controls.
- `React/Front end/src/config/` - product/module configuration, runtime config, and walkthrough scenarios.
- `React/Front end/src/services/` - API clients and integration boundaries.
- `React/Front end/src/ui.jsx` - shared UI primitives. As this grows, split into `src/ui/` files.
- `React/Front end/src/views/` - public/shareable views that are outside the authenticated module workspace.
- `React/Back end/` - deployed FastAPI wrapper used by the React frontend.
- `React/Back end/deliberation/api/app/` - main backend application package.

## Legacy And Support Areas

- `legacy/CRM/`, `legacy/Deliberation/`, `legacy/DueDiligence/` - older or reference apps. Do not mix new React/FastAPI product features into these folders unless reviving a legacy app deliberately.
- `tools/` - one-off migrations, imports, diagnostics, and scripts.
- `data/` - source/import/export data used by scripts.
- `docs/` - product, workflow, and architecture notes.
- `assets/` - reference screenshots and static design assets.
- `outputs/` - local generated output. This is ignored by git.`r`n- `runtime/logs/` - local server logs. This is ignored by git.

## Module Convention

For a new product module, prefer:

```text
src/modules/ModuleName/
  ModuleNamePage.jsx
  components/
  hooks/
  services.js
  utils.js
  __tests__/
```

Keep shared logic out of module folders only when at least two modules actually use it. Put cross-module API calls in `src/services/`, reusable UI in `src/components/` or `src/ui/`, and stable product configuration in `src/config/`.

Use the `@/` alias for new imports from `src`, for example `@/services/api` or `@/modules/CRM/CRMPage.jsx`.

