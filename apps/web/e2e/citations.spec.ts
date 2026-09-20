import { expect, test } from '@playwright/test'

// Vitest also collects *.spec.ts, and Playwright throws when suites register
// outside its runner — so the suite only registers under Playwright.
if (!process.env.VITEST) {
  test.describe('citation source preview', () => {
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

    test('marker opens the preview and stays within the message citations', async ({
      page,
    }) => {
      await page.route('**/api/chat', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            answer: 'Alpha and beta agree [1] [2].',
            citations: [
              {
                chunk_id: '11111111-1111-1111-1111-111111111111',
                document_id: '22222222-2222-2222-2222-222222222222',
                document_name: 'alpha-guide.pdf',
                position: 0,
                content: 'alpha beta gamma passage',
              },
              {
                chunk_id: '33333333-3333-3333-3333-333333333333',
                document_id: '44444444-4444-4444-4444-444444444444',
                document_name: 'beta-notes.md',
                position: 3,
                content: 'beta delta epsilon passage',
              },
            ],
          }),
        }),
      )
      await page.getByLabel(/ask a question/i).fill('What do they say?')
      await page.getByRole('button', { name: /send/i }).click()
      await expect(page.getByText(/alpha and beta agree/i)).toBeVisible()

      await page
        .getByRole('button', { name: 'Source 1: alpha-guide.pdf' })
        .click()
      const dialog = page.getByRole('dialog', { name: /alpha-guide\.pdf/i })
      await expect(dialog).toBeVisible()
      await expect(page.getByText('alpha beta gamma passage')).toBeVisible()
      await expect(page.getByText(/chunk 1 of 2/i)).toBeVisible()
      await expect(
        page.getByRole('button', { name: /previous/i }),
      ).toBeDisabled()

      await page.getByRole('button', { name: /next/i }).click()
      await expect(page.getByText('beta delta epsilon passage')).toBeVisible()
      await expect(page.getByText(/chunk 2 of 2/i)).toBeVisible()
      await expect(page.getByRole('button', { name: /next/i })).toBeDisabled()

      await page.getByRole('button', { name: /previous/i }).click()
      await expect(page.getByText('alpha beta gamma passage')).toBeVisible()

      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(
        page.getByRole('button', { name: 'Source 1: alpha-guide.pdf' }),
      ).toBeFocused()
    })

    test('hostile citation text stays inert in the preview', async ({
      page,
    }) => {
      await page.route('**/api/chat', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            answer: 'Evil says so [1].',
            citations: [
              {
                chunk_id: '77777777-7777-7777-7777-777777777777',
                document_id: '88888888-8888-8888-8888-888888888888',
                document_name: 'evil.pdf',
                position: 0,
                content:
                  '<script>alert(1)</script><a href="https://evil.test">click</a>',
              },
            ],
          }),
        }),
      )
      await page.getByLabel(/ask a question/i).fill('What is evil?')
      await page.getByRole('button', { name: /send/i }).click()
      await expect(page.getByText(/evil says so/i)).toBeVisible()

      await page.getByRole('button', { name: 'Source 1: evil.pdf' }).click()
      await expect(
        page.getByRole('dialog', { name: /evil\.pdf/i }),
      ).toBeVisible()
      await expect(
        page.getByText(
          '<script>alert(1)</script><a href="https://evil.test">click</a>',
        ),
      ).toBeVisible()
      await expect(page.locator('dialog a, [role="dialog"] a')).toHaveCount(0)
    })
  })
}
