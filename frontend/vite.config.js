import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  // The example scenario is shared with the Python package in ../examples.
  server: { fs: { allow: ['..'] } },
});
