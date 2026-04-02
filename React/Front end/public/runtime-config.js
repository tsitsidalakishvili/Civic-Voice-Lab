// Leave API_BASE_URL empty so local/dev use Vite env (.env.development / .env.production).
// For servers without a build-time URL, set API_BASE_URL here to your API origin (https://…).
window.__FS_RUNTIME_CONFIG__ = {
  API_BASE_URL: '',
  AUTH_ENABLED: false,
  AUTH_MODE: 'bearer',
  AUTH_TOKEN: '',
  AUTH_API_KEY: '',
  AUTH_HEADER_NAME: 'X-FS-API-Key',
}
