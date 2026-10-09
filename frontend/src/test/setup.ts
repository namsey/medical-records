import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

// jsdom does not implement these browser APIs.
window.scrollTo = () => {}
Element.prototype.scrollIntoView = () => {}
