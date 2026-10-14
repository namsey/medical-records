import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { App } from './App'
import { ToastProvider } from './components/ui/Toast'
import './index.css'
import { queryClient } from './lib/queryClient'

// A data router (rather than <BrowserRouter>) so screens can use useBlocker, e.g. to confirm leaving a form
// with unsaved changes. The app keeps its own <Routes>, so every path is handled by one catch-all route.
const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <ToastProvider>
        <App />
      </ToastProvider>
    ),
  },
])

const root = document.getElementById('root')
if (!root) throw new Error('Missing #root element')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
