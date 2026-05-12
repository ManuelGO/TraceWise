import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['src/test.setup.ts'],
    include: ['src/**/*.spec.ts'],
    transformMode: {
      web: [/\.[jt]sx?$/],
    },
    typecheck: {
      tsconfig: 'tsconfig.spec.json',
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
      ]
    },
  },
});
