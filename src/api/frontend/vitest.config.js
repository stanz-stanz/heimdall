import { defineConfig } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// Slice 3g.5 implementation deviation from spec §2.2: apps/signup/ does
// not render Svelte components in tests, so its harness can omit
// svelteTesting() and accept the default preprocessor chain. Component
// tests on Login.svelte / splash views fail under Vite 6 +
// @sveltejs/vite-plugin-svelte 5.x because the default CSS preprocessor
// calls Vite's `preprocessCSS` against an environment that doesn't exist
// in test-runner mode ("Cannot create proxy with a non-object as target
// or handler"). Disable the preprocessor chain — we only use plain CSS,
// no SCSS / Less / PostCSS plugins that would actually need preprocessing.
// `svelteTesting()` adds the testing-library matchers + auto-cleanup and
// is the standard Vitest companion plugin.
export default defineConfig({
  plugins: [
    svelte({ hot: false, preprocess: [] }),
    svelteTesting(),
  ],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
    globals: false,
  },
  resolve: {
    alias: {
      $lib: resolve(__dirname, 'src/lib'),
    },
  },
});
