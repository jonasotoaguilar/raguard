import { expect, test } from '@playwright/test'

// Vitest also collects *.spec.ts, and Playwright throws when suites register
// outside its runner — so the suite only registers under Playwright.
if (!process.env.VITEST) {
  test.describe('stateless chat thread', () => {
    test.beforeEach(async ({ page }) => {
      await page.route('**/api/auth/login', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ message: 'ok' }),
        }),
      )
      await page.goto('/login?redirect=%2Fchat')
      await page.getByLabel(/email/i).fill('member@example.com')
      await page.getByLabel(/password/i).fill('correct-password')
      await page.getByRole('button', { name: /sign in/i }).click()
      await expect(page).toHaveURL(/\/chat/)
    })

    test('asks a question and renders the grounded answer with sources', async ({
      page,
    }) => {
      await page.route('**/api/chat', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            answer: 'Alpha guide says so [1].',
            citations: [
              {
                chunk_id: '11111111-1111-1111-1111-111111111111',
                document_id: '22222222-2222-2222-2222-222222222222',
                document_name: 'alpha-guide.pdf',
                position: 0,
                content: 'alpha beta gamma',
              },
            ],
          }),
        }),
      )
      await page.getByLabel(/ask a question/i).fill('What is alpha?')
      await page.getByRole('button', { name: /send/i }).click()
      await expect(page.getByText('What is alpha?')).toBeVisible()
      await expect(page.getByText(/alpha guide says so/i)).toBeVisible()
      await expect(
        page.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
      ).toBeVisible()
    })

    test('shows a pending status with no fabricated answer, then cancels', async ({
      page,
    }) => {
      await page.route('**/api/chat', () => {
        // Never fulfills: the request stays pending until cancelled.
      })
      await page.getByLabel(/ask a question/i).fill('What is alpha?')
      await page.getByRole('button', { name: /send/i }).click()
      await expect(page.getByRole('status')).toHaveText(
        /searching your documents/i,
      )
      await expect(page.getByText('What is alpha?')).toBeVisible()
      await page.getByRole('button', { name: /cancel/i }).click()
      await expect(page.getByRole('status')).toHaveCount(0)
    })

    test('renders neutral copy when nothing relevant is found', async ({
      page,
    }) => {
      await page.route('**/api/chat', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ answer: null, citations: [] }),
        }),
      )
      await page.getByLabel(/ask a question/i).fill('omega?')
      await page.getByRole('button', { name: /send/i }).click()
      await expect(
        page.getByText(/no relevant documents found for this question/i),
      ).toBeVisible()
    })
  })
}
