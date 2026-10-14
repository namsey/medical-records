import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

/** Go back one step in the app's history, or to `fallback` when the page was opened directly (no in-app history). */
export function useGoBack(fallback: string): () => void {
  const navigate = useNavigate()
  return useCallback(() => {
    const index = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (index > 0) navigate(-1)
    else navigate(fallback, { replace: true })
  }, [navigate, fallback])
}
