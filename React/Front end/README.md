# React Front end (production)

Run:
```
npm install
npm run dev
```

Env:
- `VITE_API_BASE_URL` controls the backend base URL.
- Use `.env.production` when deploying.
- Use `.env.development` for local dev if you want a separate file.

### Deploy to Vercel
1. Import the GitHub repo into Vercel.
2. Set the Root Directory to `React/Front end`.
3. Build command: `npm run build`
4. Output directory: `dist`
5. Set environment variable:
   - **`VITE_API_BASE_URL`** = your Render (or other) API origin, e.g. `https://fs-udmk.onrender.com`
   - Required if you do not rely on a committed `.env.production` during build. Without it, the browser may try `localhost:8010` and CRM calls (e.g. `GET /crm/events`) fail with **Failed to fetch** while some POSTs appear to work.
   - **`VITE_OIDC_PROVIDER`** = `google` or `entra`, matching the backend's single configured provider. This is provider selection, not a secret.
   - Leave **`VITE_PUBLIC_BUSINESS_ROUTES_ENABLED=false`** until the backend explicitly allows every public method and path after privacy/signature review.
   - Leave **`VITE_ANALYTICS_ENABLED=false`** for private releases. Analytics mounts only after an explicit privacy-approved opt-in.
6. On Render, set **`CORS_ORIGINS`** to your real frontend origin(s), comma-separated, e.g. `https://your-app.vercel.app,https://your-custom-domain.com` (default regex already allows `*.vercel.app` and `*.netlify.app`).
7. Optional: edit `public/runtime-config.js` **on the deployed host** to set `API_BASE_URL` if you cannot inject Vite env at build time (leave empty when using `VITE_API_BASE_URL`).
8. Deploy.

### Organization-session migration

- The browser redirects to `/auth/login`, then bootstraps the HttpOnly session and CSRF token from `/auth/me`.
- Every API request includes cookies; mutations send `X-FS-CSRF`. Provider tokens, session IDs, allowlists, staff emails, and shared keys must not be placed in Vite or runtime configuration.
- Prefer same-site custom `app.<organization>` and `api.<organization>` domains. Vercel-to-Render service domains require exact credentialed CORS and a backend `Secure; SameSite=None` cookie, and may still be blocked by browser third-party-cookie policy.
- Public business routes fail closed by default. Frontend route visibility never grants backend authorization.
- Rollback is backend environment-selected only. The normal frontend contains no credential input. `VITE_EMERGENCY_AUTH_GATE_ENABLED` is reserved for a separately reviewed migration screen and remains false; it never contains a secret.
- On logout, 401, revocation, or principal change, clear in-memory GET and CSRF state. Do not persist sensitive responses in browser storage.
- The campaign seed contains synthetic records only. Production builds also fail-safe against copying the retired `ade-demo.pdf` and `ade-demo-test.pdf` paths into deploy artifacts.

---

# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
