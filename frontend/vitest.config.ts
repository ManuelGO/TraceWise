import { defineConfig } from 'vitest/config';
import angular from '@vitejs/plugin-angular';
import { getVitestConfig } from 'ng-vitest';

export default defineConfig(
  getVitestConfig({
    plugins: [angular()],
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: [],
      include: ['src/**/*.spec.ts'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'json', 'html'],
        exclude: [
          'node_modules/',
          'src/test.ts',
        ]
      },
    },
  })
);
