import * as pdfjs from 'pdfjs-dist'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { errorMessage, fetchBytes } from '@/lib/api'
import { ErrorMessage, LoadingState } from '../ui/feedback'

// Android's Chrome cannot show PDFs inline, so PDFs are drawn by pdf.js inside the page instead.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const MAX_CANVAS_PIXELS = 12_000_000

interface PdfViewerProps {
  url: string
  /** 1 = fit to the available width. */
  zoom: number
}

export function PdfViewer({ url, zoom }: PdfViewerProps) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [width, setWidth] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    let loadingTask: PDFDocumentLoadingTask | null = null
    let cancelled = false
    setPdf(null)
    setError(null)

    async function load() {
      try {
        const bytes = await fetchBytes(url, controller.signal)
        loadingTask = pdfjs.getDocument({
          data: new Uint8Array(bytes),
          standardFontDataUrl: '/pdfjs/standard_fonts/',
          wasmUrl: '/pdfjs/wasm/',
          iccUrl: '/pdfjs/iccs/',
        })
        const loaded = await loadingTask.promise
        if (cancelled) return
        setPdf(loaded)
      } catch (loadError) {
        if (cancelled || (loadError instanceof DOMException && loadError.name === 'AbortError')) return
        setError(loadError instanceof Error && loadError.name === 'InvalidPDFException' ? 'This PDF could not be displayed. You can still download it.' : errorMessage(loadError))
      }
    }
    void load()

    return () => {
      cancelled = true
      controller.abort()
      if (loadingTask) void loadingTask.destroy()
    }
  }, [url, attempt])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    setWidth(element.clientWidth)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={containerRef} className="w-full overflow-auto rounded-xl bg-wash p-2" style={{ minHeight: '40dvh' }}>
      {error && <ErrorMessage message={error} onRetry={() => setAttempt((value) => value + 1)} />}
      {!pdf && !error && <LoadingState label="Opening PDF…" />}
      {pdf && width > 0 && (
        <div className="flex w-max min-w-full flex-col items-center gap-3">
          {Array.from({ length: pdf.numPages }, (_, index) => (
            <PdfPage key={index + 1} pdf={pdf} pageNumber={index + 1} cssWidth={Math.max(120, (width - 16) * zoom)} />
          ))}
        </div>
      )}
    </div>
  )
}

interface PdfPageProps {
  pdf: PDFDocumentProxy
  pageNumber: number
  cssWidth: number
}

/** One page, drawn only once it is close to the screen so long documents stay fast. */
function PdfPage({ pdf, pageNumber, cssWidth }: PdfPageProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [visible, setVisible] = useState(pageNumber <= 2)
  const [aspect, setAspect] = useState(1.414) // height / width, A4 until the real page is known
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const element = wrapperRef.current
    if (!element || visible) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setVisible(true)
      },
      { rootMargin: '800px 0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    let task: RenderTask | null = null

    async function draw() {
      try {
        const page = await pdf.getPage(pageNumber)
        const base = page.getViewport({ scale: 1 })
        const scale = cssWidth / base.width
        const cssViewport = page.getViewport({ scale })
        setAspect(cssViewport.height / cssViewport.width)

        let outputScale = Math.min(window.devicePixelRatio || 1, 2)
        const pixels = cssViewport.width * cssViewport.height * outputScale * outputScale
        if (pixels > MAX_CANVAS_PIXELS) outputScale = Math.sqrt(MAX_CANVAS_PIXELS / (cssViewport.width * cssViewport.height))

        const viewport = page.getViewport({ scale: scale * outputScale })
        const canvas = canvasRef.current
        if (!canvas || cancelled) return
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        canvas.style.width = `${Math.floor(cssViewport.width)}px`
        canvas.style.height = `${Math.floor(cssViewport.height)}px`
        task = page.render({ canvas, viewport })
        await task.promise
        setFailed(false)
      } catch (drawError) {
        if (!cancelled && !(drawError instanceof Error && drawError.name === 'RenderingCancelledException')) setFailed(true)
      }
    }
    void draw()

    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [pdf, pageNumber, cssWidth, visible])

  return (
    <div ref={wrapperRef} className="bg-white shadow-sm" style={{ width: cssWidth, minHeight: cssWidth * aspect }} aria-label={`Page ${pageNumber} of ${pdf.numPages}`}>
      {failed ? <p className="p-4 text-sm text-danger-700">Page {pageNumber} could not be drawn.</p> : <canvas ref={canvasRef} className="block" />}
    </div>
  )
}
