// Leave API_BASE_URL empty so local/dev use Vite env (.env.development / .env.production).
// For servers without a build-time URL, set API_BASE_URL here to your API origin (https://…).
window.__FS_RUNTIME_CONFIG__ = {
  API_BASE_URL: '',
  AUTH_ENABLED: true,
  AUTH_MODE: 'session',
  OIDC_PROVIDER: '',
  PUBLIC_BUSINESS_ROUTES_ENABLED: false,
  EMERGENCY_AUTH_GATE_ENABLED: false,
}
