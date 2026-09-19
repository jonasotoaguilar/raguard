import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'

/** Shared Query defaults per DESIGN.md: stable refs 30s, no 4xx retry. */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        throwOnError: false,
        retry: (count, error) => {
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          )
            return false
          return count < 2
        },
      },
      mutations: { retry: 0, throwOnError: false },
    },
  })
}

export const queryClient = createAppQueryClient()
