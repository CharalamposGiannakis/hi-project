import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
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
