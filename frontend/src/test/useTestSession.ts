import { useCallback, useEffect, useRef, useState } from 'react'
import { sessionSocketUrl } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { CallMode, Issue, ScenarioResult, SessionSummary, TraceEvent } from '../lib/types'

export type SessionStatus = 'idle' | 'connecting' | 'live' | 'ended' | 'error'

interface StartOptions {
  agentId: string
  version: number
  variables: Record<string, string>
  mode: CallMode
  scenarioId?: string
}

const ICE_GATHERING_TIMEOUT_MS = 2000

/**
 * One simulated call over the /api/sessions/ws protocol (see backend/app/api/sessions.py).
 * Voice calls also open a WebRTC connection; its offer/answer travel over the same WebSocket.
 */
export function useTestSession() {
  const token = useAuth((s) => s.token)
  const [status, setStatus] = useState<SessionStatus>('idle')
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [session, setSession] = useState<SessionSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<Issue[]>([])
  const [mic, setMic] = useState<MediaStream | null>(null)
  const [muted, setMuted] = useState(false)
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const socket = useRef<WebSocket | null>(null)
  const peer = useRef<RTCPeerConnection | null>(null)
  const speaker = useRef<HTMLAudioElement | null>(null)

  const close = useCallback(() => {
    socket.current?.close()
    socket.current = null
    peer.current?.close()
    peer.current = null
    setMic((stream) => {
      stream?.getTracks().forEach((t) => t.stop())
      return null
    })
    if (speaker.current) speaker.current.srcObject = null
  }, [])

  useEffect(() => close, [close])

  const start = useCallback(
    async ({ agentId, version, variables, mode, scenarioId }: StartOptions) => {
      if (!token) return
      close()
      setResult(null)
      setEvents([])
      setSession(null)
      setError(null)
      setIssues([])
      setMuted(false)
      setStatus('connecting')

      // Ask for the microphone first, so a refusal never leaves a half-started call behind.
      let offer: RTCSessionDescriptionInit | null = null
      if (mode === 'voice') {
        try {
          const voice = await openVoicePeer((remote) => {
            if (!speaker.current) speaker.current = new Audio()
            speaker.current.srcObject = remote
            speaker.current.play().catch(() => {})
          })
          peer.current = voice.pc
          setMic(voice.mic)
          offer = voice.offer
        } catch (e) {
          close()
          setError(
            e instanceof DOMException && e.name === 'NotAllowedError'
              ? 'Mikrofon izni verilmedi. Tarayıcı ayarlarından bu siteye mikrofon izni verin.'
              : 'Mikrofon açılamadı.',
          )
          setStatus('error')
          return
        }
      }

      const ws = new WebSocket(sessionSocketUrl())
      socket.current = ws
      ws.onopen = () =>
        ws.send(JSON.stringify({ type: 'start', token, agent_id: agentId, version, variables, mode, scenario_id: scenarioId }))
      ws.onmessage = async (msg) => {
        const data = JSON.parse(msg.data)
        if (data.type === 'session') {
          setSession(data.session)
          if (offer) ws.send(JSON.stringify({ type: 'webrtc_offer', sdp: offer.sdp, sdp_type: offer.type }))
          else setStatus('live')
        } else if (data.type === 'webrtc_answer') {
          await peer.current?.setRemoteDescription({ type: data.sdp_type, sdp: data.sdp })
          setStatus('live')
        } else if (data.type === 'event') {
          const event = data.event as TraceEvent
          setEvents((prev) => [...prev, event])
          if (event.type === 'session_ended') {
            setStatus('ended')
            // Let the goodbye finish playing before the audio goes away.
            setTimeout(() => peer.current?.close(), 500)
          }
        } else if (data.type === 'simulation_result') {
          setResult(data.result)
        } else if (data.type === 'error') {
          setError(data.message)
          setIssues(data.issues ?? [])
          setStatus('error')
          close()
        }
      }
      ws.onerror = () => {
        setError('Sunucuyla bağlantı kurulamadı.')
        setStatus('error')
      }
      ws.onclose = () => {
        if (socket.current === ws) socket.current = null
        setStatus((s) => (s === 'live' || s === 'connecting' ? 'ended' : s))
      }
    },
    [token, close],
  )

  const send = useCallback((text: string) => {
    socket.current?.send(JSON.stringify({ type: 'user_text', text }))
  }, [])

  const hangup = useCallback(() => {
    socket.current?.send(JSON.stringify({ type: 'hangup' }))
  }, [])

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      mic?.getAudioTracks().forEach((t) => (t.enabled = m))
      return !m
    })
  }, [mic])

  const reset = useCallback(() => {
    close()
    setStatus('idle')
    setEvents([])
    setSession(null)
    setError(null)
    setIssues([])
    setResult(null)
  }, [close])

  return { status, events, session, error, issues, mic, muted, result, start, send, hangup, reset, toggleMute }
}

/** Microphone in, agent audio out. Waits for ICE gathering: the server takes no trickle ICE. */
async function openVoicePeer(onRemoteAudio: (stream: MediaStream) => void) {
  const mic = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  const pc = new RTCPeerConnection()
  // Pipecat expects audio on the first transceiver.
  pc.addTransceiver(mic.getAudioTracks()[0], { direction: 'sendrecv' })
  pc.createDataChannel('chat')
  pc.ontrack = (e) => onRemoteAudio(e.streams[0] ?? new MediaStream([e.track]))
  await pc.setLocalDescription(await pc.createOffer())
  await new Promise<void>((resolve) => {
    if (pc.iceGatheringState === 'complete') return resolve()
    pc.addEventListener('icegatheringstatechange', () => pc.iceGatheringState === 'complete' && resolve())
    setTimeout(resolve, ICE_GATHERING_TIMEOUT_MS)
  })
  return { pc, mic, offer: pc.localDescription! }
}

/** The bot owes a reply: the caller spoke last and the call is still running. */
export function isBotThinking(events: TraceEvent[]): boolean {
  for (let i = events.length - 1; i >= 0; i--) {
    const t = events[i].type
    if (t === 'user_message') return true
    if (t === 'bot_message' || t === 'say' || t === 'session_ended' || t === 'error') return false
  }
  return false
}
