import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./test-setup.ts'],
    passWithNoTests: true,
    // Playwright specs mock the full API via page.route and run under the
    // Playwright runner only; exclude them from Vitest collection (the specs
    // also carry an `if (!process.env.VITEST)` registration guard as a
    // second line of defense).
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
