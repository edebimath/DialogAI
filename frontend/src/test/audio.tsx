import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'

/** Live microphone level, so the tester can see the browser is actually hearing them. */
export function MicLevel({ stream, muted }: { stream: MediaStream; muted: boolean }) {
  const bar = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const ctx = new AudioContext()
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 512
    ctx.createMediaStreamSource(stream).connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)
    let frame = 0
    const tick = () => {
      analyser.getByteTimeDomainData(samples)
      let peak = 0
      for (const s of samples) peak = Math.max(peak, Math.abs(s - 128))
      if (bar.current) bar.current.style.width = `${Math.min(100, (peak / 64) * 100)}%`
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => {
      cancelAnimationFrame(frame)
      ctx.close()
    }
  }, [stream])

  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
      <div ref={bar} className={muted ? 'h-full bg-slate-300' : 'h-full bg-emerald-500 transition-[width] duration-75'} />
    </div>
  )
}

/** Plays a stored call recording (fetched with the auth header, which <audio src> can't send). */
export function RecordingPlayer({ sessionId }: { sessionId: string }) {
  const token = useAuth((s) => s.token)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    fetch(`/api/sessions/${sessionId}/recording`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => setError(true))
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [sessionId, token])

  if (error) return <p className="text-xs text-rose-600">Kayıt yüklenemedi.</p>
  if (!url) return <p className="text-xs text-slate-400">Kayıt yükleniyor…</p>
  return <audio controls src={url} className="h-8 w-full" />
}
