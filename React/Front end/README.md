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
6. On Render, set **`CORS_ORIGINS`** to your real frontend origin(s), comma-separated, e.g. `https://your-app.vercel.app,https://your-custom-domain.com` (default regex already allows `*.vercel.app` and `*.netlify.app`).
7. Optional: edit `public/runtime-config.js` **on the deployed host** to set `API_BASE_URL` if you cannot inject Vite env at build time (leave empty when using `VITE_API_BASE_URL`).
8. Deploy.

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
