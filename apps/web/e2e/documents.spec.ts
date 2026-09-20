import { expect, type Page, test } from '@playwright/test'

// Vitest also collects *.spec.ts, and Playwright throws when suites register
// outside its runner — so the suite only registers under Playwright.
if (!process.env.VITEST) {
  const DOC_ID = '11111111-1111-1111-1111-111111111111'
  const MD_ID = '22222222-2222-2222-2222-222222222222'
  const PDF_ID = '33333333-3333-3333-3333-333333333333'

  const INDEXED_DOC = {
    id: DOC_ID,
    name: 'alpha-guide.pdf',
    status: 'indexed',
    failure_reason: null,
  }

  const FAILED_DOC = {
    id: MD_ID,
    name: 'beta-notes.md',
    status: 'failed',
    failure_reason: 'malformed',
  }

  const PENDING_DOC = {
    id: DOC_ID,
    name: 'alpha-guide.pdf',
    status: 'pending',
    failure_reason: null,
  }

  function json(body: unknown, status = 200) {
    return {
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    }
  }

  async function loginToDocuments(page: Page) {
    await page.route('**/api/auth/login', (route) =>
      route.fulfill(json({ message: 'ok' })),
    )
    await page.goto('/login?redirect=%2Fdocuments')
    await page.getByLabel(/email/i).fill('member@example.com')
    await page.getByLabel(/password/i).fill('correct-password')
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).toHaveURL(/\/documents/)
  }

  test.describe('documents access', () => {
    test('unauthenticated /documents lands on /login with the return path', async ({
      page,
    }) => {
      await page.goto('/documents')
      await expect(page).toHaveURL(/\/login\?redirect=%2Fdocuments/)
      await expect(page.getByLabel(/email/i)).toBeVisible()
      await expect(page.getByLabel(/password/i)).toBeVisible()
    })
  })

  test.describe('documents library', () => {
    test('member sees the table with scoped headers, status, and detail links', async ({
      page,
    }) => {
      await page.route('**/api/documents', (route) =>
        route.fulfill(json({ documents: [INDEXED_DOC, FAILED_DOC] })),
      )
      await loginToDocuments(page)

      await expect(
        page.getByRole('heading', { name: /documents/i }),
      ).toBeVisible()
      await expect(page.getByRole('columnheader')).toHaveText([
        'Name',
        'Status',
      ])
      await expect(
        page.getByRole('link', { name: 'alpha-guide.pdf' }),
      ).toHaveAttribute('href', `/documents/${DOC_ID}`)
      await expect(
        page.getByRole('link', { name: 'beta-notes.md' }),
      ).toHaveAttribute('href', `/documents/${MD_ID}`)
      await expect(page.getByText('Indexed')).toBeVisible()
      await expect(page.getByText(/Failed/)).toBeVisible()
      await expect(page.getByText(/malformed/)).toBeVisible()
    })

    test('uploads PDF and Markdown files through the labelled input', async ({
      page,
    }) => {
      const uploaded = [
        { ...PENDING_DOC, id: MD_ID, name: 'notes.md' },
        { ...PENDING_DOC, id: PDF_ID, name: 'scan.pdf' },
      ]
      let posts = 0
      let lists = 0
      await page.route('**/api/documents', (route) => {
        if (route.request().method() === 'POST') {
          const doc = uploaded[posts] ?? uploaded[uploaded.length - 1]
          posts += 1
          return route.fulfill(json(doc, 201))
        }
        lists += 1
        return route.fulfill(json({ documents: lists === 1 ? [] : uploaded }))
      })
      await loginToDocuments(page)
      await expect(page.getByText(/no documents yet/i)).toBeVisible()

      await page.getByLabel(/choose document files/i).setInputFiles([
        {
          name: 'notes.md',
          mimeType: 'text/markdown',
          buffer: Buffer.from('# notes\n'),
        },
        {
          name: 'scan.pdf',
          mimeType: 'application/pdf',
          buffer: Buffer.from(
            '%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n',
          ),
        },
      ])

      await expect(page.getByRole('link', { name: 'notes.md' })).toBeVisible()
      await expect(page.getByRole('link', { name: 'scan.pdf' })).toBeVisible()
      await expect(page.getByText('Pending')).toBeVisible()
    })

    test('pending row refreshes to indexed on the next poll', async ({
      page,
    }) => {
      let lists = 0
      await page.route('**/api/documents', (route) => {
        lists += 1
        return route.fulfill(
          json({ documents: [lists === 1 ? PENDING_DOC : INDEXED_DOC] }),
        )
      })
      await loginToDocuments(page)

      await expect(page.getByText('Pending')).toBeVisible()
      await expect(page.getByText('Indexed')).toBeVisible({ timeout: 15000 })
      await expect(
        page.getByRole('link', { name: 'alpha-guide.pdf' }),
      ).toBeVisible()
    })

    test('detail route shows status, id metadata, and a back link', async ({
      page,
    }) => {
      await page.route('**/api/documents', (route) =>
        route.fulfill(json({ documents: [INDEXED_DOC] })),
      )
      await page.route('**/api/documents/*', (route) =>
        route.fulfill(json(INDEXED_DOC)),
      )
      await loginToDocuments(page)

      await page.getByRole('link', { name: 'alpha-guide.pdf' }).click()
      await expect(page).toHaveURL(`/documents/${DOC_ID}`)
      await expect(
        page.getByRole('heading', { name: 'alpha-guide.pdf' }),
      ).toBeVisible()
      await expect(page.getByText('Indexed')).toBeVisible()
      await expect(page.getByText(DOC_ID)).toBeVisible()

      await page.getByRole('link', { name: /back to documents/i }).click()
      await expect(page).toHaveURL(/\/documents$/)
    })

    test('hostile names render as inert text', async ({ page }) => {
      const evil = '<script>alert(1)</script>.pdf'
      await page.route('**/api/documents', (route) =>
        route.fulfill(
          json({
            documents: [
              {
                id: DOC_ID,
                name: evil,
                status: 'indexed',
                failure_reason: null,
              },
            ],
          }),
        ),
      )
      await loginToDocuments(page)

      await expect(page.getByText(evil)).toBeVisible()
      await expect(page.locator('script')).toHaveCount(0)
    })
  })
}
