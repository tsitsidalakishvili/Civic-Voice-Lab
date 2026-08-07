import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { privateReleaseGuard } from './build/privateRelease.js'

// https://vite.dev/config/
const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => ({
  plugins: [
    privateReleaseGuard({ production: mode === 'production', outDir: resolve(__dirname, 'dist') }),
    react(),
  ],
  resolve: {
    alias: [
      {
        find: '@',
        replacement: resolve(__dirname, 'src'),
      },
      {
        find: /^leaflet$/,
        replacement: resolve(__dirname, 'node_modules/leaflet/dist/leaflet-src.js'),
      },
    ],
  },
  optimizeDeps: {
    include: ['leaflet'],
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
}))

