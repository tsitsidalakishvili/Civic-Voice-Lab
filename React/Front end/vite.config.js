import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: /^leaflet$/,
        replacement: resolve(__dirname, 'node_modules/leaflet/dist/leaflet-src.js'),
      },
    ],
  },
  optimizeDeps: {
    include: ['leaflet'],
  },
})
