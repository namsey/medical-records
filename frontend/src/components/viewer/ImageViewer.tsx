import { useState } from 'react'
import { ErrorMessage, LoadingState } from '../ui/feedback'

interface ImageViewerProps {
  url: string
  alt: string
  /** 1 = fit to the available width. */
  zoom: number
}

export function ImageViewer({ url, alt, zoom }: ImageViewerProps) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)

  return (
    <div className="w-full overflow-auto rounded-xl bg-wash p-2" style={{ minHeight: '40dvh' }}>
      {state === 'loading' && <LoadingState label="Opening image…" />}
      {state === 'error' && <ErrorMessage message="This image could not be loaded." onRetry={() => { setState('loading'); setAttempt((value) => value + 1) }} />}
      <img
        key={attempt}
        src={url}
        alt={alt}
        onLoad={() => setState('ready')}
        onError={() => setState('error')}
        className={`mx-auto block h-auto bg-white shadow-sm ${state === 'ready' ? '' : 'hidden'}`}
        style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? '100%' : 'none' }}
      />
    </div>
  )
}
