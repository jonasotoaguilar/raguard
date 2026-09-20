import { createRootRoute, Outlet } from '@tanstack/react-router'
import { AppShell, defaultNav } from '../app/shell'

/** Auth-aware layout: sidebar, tenant header, skip link; focus lands on main. */
export const RootRoute = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <AppShell tenantName="raguard" nav={defaultNav}>
      <Outlet />
    </AppShell>
  )
}
