import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [svelte()],
  // Both pages are real static files, so viewer reloads also work behind Caddy.
  build: {
    rolldownOptions: {
      input: {
        builder: resolve(import.meta.dirname, 'index.html'),
        jsonViewer: resolve(import.meta.dirname, 'json-viewer.html'),
      },
    },
  },
  server: {
    // The backend's CORS policy allows only this origin, so never fall back to another port.
    port: 5173,
    strictPort: true,
    // The example scenario is shared with the Python package in ../examples.
    fs: { allow: ['..'] },
  },
  // Component tests mount Svelte's browser build in jsdom.
  resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
});
