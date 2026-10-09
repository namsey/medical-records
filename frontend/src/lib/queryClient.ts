import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

export const ME_KEY = ['me'] as const

function handleUnauthorized(error: unknown) {
  // Session expired or was revoked: dropping the cached user sends the app back to the login page.
  if (error instanceof ApiError && error.status === 401) {
    queryClient.setQueryData(ME_KEY, null)
  }
}

export const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleUnauthorized }),
  mutationCache: new MutationCache({ onError: handleUnauthorized }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2,
    },
  },
})
