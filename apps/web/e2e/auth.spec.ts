import { expect, test } from '@playwright/test'

// Vitest also collects *.spec.ts, and Playwright throws when suites register
// outside its runner — so the suite only registers under Playwright.
if (!process.env.VITEST) {
  test.describe('auth shell', () => {
    test('unauthenticated /chat lands on /login with the return path', async ({
      page,
    }) => {
      await page.goto('/chat')
      await expect(page).toHaveURL(/\/login\?redirect=%2Fchat/)
      await expect(page.getByLabel(/email/i)).toBeVisible()
      await expect(page.getByLabel(/password/i)).toBeVisible()
    })

    test('failed login shows the envelope error and stays put', async ({
      page,
    }) => {
      await page.route('**/api/auth/login', (route) =>
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'authentication_failed',
              message: 'Invalid email or password',
            },
          }),
        }),
      )
      await page.goto('/login')
      await page.getByLabel(/email/i).fill('member@example.com')
      await page.getByLabel(/password/i).fill('wrong-password')
      await page.getByRole('button', { name: /sign in/i }).click()
      await expect(page.getByText(/invalid email or password/i)).toBeVisible()
      await expect(page).toHaveURL(/\/login/)
    })

    test('successful login follows the return path', async ({ page }) => {
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
  })
}
