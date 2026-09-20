import { QueryClientProvider } from '@tanstack/react-query'
import {
  createRoute,
  createRouter,
  RouterProvider,
  redirect,
} from '@tanstack/react-router'
import { createRoot } from 'react-dom/client'
import { authGuardRedirect, setUnauthorizedHandler } from '../api/client'
import { RootRoute } from '../routes/__root'
import { AdminPage } from '../routes/admin'
import { ChatPage } from '../routes/chat'
import { DocumentDetailPage, DocumentsPage } from '../routes/documents'
import { loginRoute } from '../routes/login'
import { queryClient } from './query-client'

/** Anonymous users go to /login with the return path preserved. */
function protect(path: string): void {
  const target = authGuardRedirect(path)
  if (target) throw redirect({ to: '/login', search: { redirect: path } })
}

const indexRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/',
  beforeLoad: ({ location }) => {
    protect(location.pathname)
    throw redirect({ to: '/chat' })
  },
  component: () => null,
})

const chatRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/chat',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: ChatPage,
})

const documentsRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/documents',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: DocumentsPage,
})

export const documentDetailRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/documents/$documentId',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: DocumentDetailRouteView,
})

function DocumentDetailRouteView() {
  const { documentId } = documentDetailRoute.useParams()
  return <DocumentDetailPage documentId={documentId} />
}

const adminRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/admin',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: AdminPage,
})

const adminUsersRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/admin/users',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: AdminPage,
})

const adminRolesRoute = createRoute({
  getParentRoute: () => RootRoute,
  path: '/admin/roles',
  beforeLoad: ({ location }) => protect(location.pathname),
  component: AdminPage,
})

const routeTree = RootRoute.addChildren([
  loginRoute,
  indexRoute,
  chatRoute,
  documentsRoute,
  documentDetailRoute,
  adminRoute,
  adminUsersRoute,
  adminRolesRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

/** Mount the app; background 401s reroute to /login with the return path. */
export function startApp(selector = '#root'): void {
  setUnauthorizedHandler((returnPath) => {
    void router.navigate({ to: '/login', search: { redirect: returnPath } })
  })
  const el = document.querySelector(selector)
  if (!el) throw new Error(`startApp: no element matches ${selector}`)
  createRoot(el).render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}
