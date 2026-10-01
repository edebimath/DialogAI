import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bot, History, Keyboard, Loader2, Mic, MicOff, PhoneCall, PhoneOff, RotateCcw, Send, Square, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode, type RefObject } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { Button, Field, Input, Select } from '../components/ui'
import { IssueList } from '../editor/Inspector'
import { useEditor } from '../editor/store'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'
import type { CallMode, Scenario, SessionDetail, SessionSummary, TraceEvent, Version } from '../lib/types'
import { StatusBadge, VerdictCard } from '../scenarios/Verdict'
import { MicLevel, RecordingPlayer } from './audio'
import Timeline, { type NodeInfo } from './Timeline'
import { isBotThinking, useTestSession } from './useTestSession'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'medium' })

/** Right-hand slide-over: run a simulated call against the flow and watch everything it does. */
export default function TestDrawer({
  agentId,
  ensureSaved,
  onClose,
}: {
  agentId: string
  ensureSaved: () => Promise<void>
  onClose: () => void
}) {
  const [tab, setTab] = useState<'live' | 'history'>('live')
  const [details, setDetails] = useState(true)
  const [replay, setReplay] = useState<SessionDetail | null>(null)
  const call = useTestSession()
  const { nodes, variables, select, setTrace } = useEditor(
    useShallow((s) => ({ nodes: s.nodes, variables: s.variables, select: s.select, setTrace: s.setTrace })),
  )

  const nodeInfo = useMemo(() => {
    const info: Record<string, NodeInfo> = {}
    for (const n of nodes) info[n.id] = { label: n.data.label ?? '', kind: n.data.kind }
    return info
  }, [nodes])

  const shown: TraceEvent[] = tab === 'history' && replay ? replay.events : call.events

  // Mirror the call onto the canvas: the current node glows, visited nodes stay marked.
  useEffect(() => {
    const entered = shown.filter((e) => e.type === 'node_entered' && e.node_id).map((e) => e.node_id!)
    const ended = shown.some((e) => e.type === 'session_ended')
    setTrace({ active: ended ? null : (entered.at(-1) ?? null), visited: [...new Set(entered)] })
  }, [shown, setTrace])
  useEffect(() => () => setTrace({ active: null, visited: [] }), [setTrace])

  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [shown.length])

  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-[420px] max-w-full flex-col border-l border-slate-200 bg-slate-50 shadow-2xl">
      <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <div className="flex rounded-md bg-slate-100 p-0.5 text-sm">
          {(['live', 'history'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx('rounded px-2.5 py-1', tab === t ? 'bg-white font-medium shadow-sm' : 'text-slate-500')}
            >
              {t === 'live' ? 'Test çağrısı' : 'Geçmiş'}
            </button>
          ))}
        </div>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-500">
          <input type="checkbox" checked={details} onChange={(e) => setDetails(e.target.checked)} />
          Sistem olayları
        </label>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Kapat">
          <X size={16} />
        </Button>
      </header>

      {tab === 'live' ? (
        <LiveCall
          agentId={agentId}
          call={call}
          variables={variables}
          ensureSaved={ensureSaved}
          scroller={scroller}
          timeline={<Timeline events={call.events} nodes={nodeInfo} details={details} onNodeClick={select} />}
        />
      ) : (
        <HistoryTab
          agentId={agentId}
          replay={replay}
          setReplay={setReplay}
          scroller={scroller}
          timeline={replay && <Timeline events={replay.events} nodes={nodeInfo} details={details} onNodeClick={select} />}
        />
      )}
    </aside>
  )
}

function LiveCall({
  agentId,
  call,
  variables,
  ensureSaved,
  scroller,
  timeline,
}: {
  agentId: string
  call: ReturnType<typeof useTestSession>
  variables: { name: string; default: string | null }[]
  ensureSaved: () => Promise<void>
  scroller: RefObject<HTMLDivElement | null>
  timeline: ReactNode
}) {
  const [version, setVersion] = useState(0)
  const [mode, setMode] = useState<CallMode>('voice')
  const [values, setValues] = useState<Record<string, string>>({})
  const [text, setText] = useState('')
  const [scenarioId, setScenarioId] = useState('')
  const versions = useQuery({ queryKey: ['versions', agentId], queryFn: () => api<Version[]>(`/api/agents/${agentId}/versions`) })
  const scenarios = useQuery({
    queryKey: ['scenarios', agentId],
    queryFn: () => api<Scenario[]>(`/api/agents/${agentId}/scenarios`),
    enabled: mode === 'simulation',
  })
  const simulating = mode === 'simulation'
  const thinking = call.status === 'live' && isBotThinking(call.events)
  const chosenScenario = scenarioId || scenarios.data?.[0]?.id || ''

  async function start() {
    if (version === 0) await ensureSaved()
    const vars: Record<string, string> = {}
    for (const v of variables) if (v.name && values[v.name] !== undefined) vars[v.name] = values[v.name]
    call.start({ agentId, version, variables: vars, mode, scenarioId: simulating ? chosenScenario : undefined })
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!text.trim() || call.status !== 'live') return
    call.send(text.trim())
    setText('')
  }

  if (call.status === 'idle' || call.status === 'error') {
    return (
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <p className="text-sm text-slate-600">
          Ajanla bir çağrıyı simüle edin. Arka planda olan her şey (kart geçişleri, fonksiyonlar, değişkenler, gecikmeler) burada ve canvas
          üzerinde görünür.
        </p>
        <div className="grid grid-cols-3 gap-2">
          {(
            [
              ['voice', Mic, 'Sesli', 'Mikrofonla konuşun'],
              ['text', Keyboard, 'Yazılı', 'Hızlı, STT/TTS yok'],
              ['simulation', Bot, 'Simüle', 'Bir LLM arayan olur'],
            ] as const
          ).map(([value, Icon, title, hint]) => (
            <button
              key={value}
              onClick={() => setMode(value)}
              className={clsx(
                'rounded-lg border p-3 text-left',
                mode === value ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 bg-white hover:border-slate-300',
              )}
            >
              <div className="flex items-center gap-1.5 text-sm font-medium">
                <Icon size={14} /> {title}
              </div>
              <div className="text-xs text-slate-500">{hint}</div>
            </button>
          ))}
        </div>
        <Field label="Test edilecek akış">
          <Select value={version} onChange={(e) => setVersion(Number(e.target.value))}>
            <option value={0}>Taslak (kaydedilmemiş değişiklikler kaydedilir)</option>
            {versions.data?.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version} {v.note && `– ${v.note}`}
              </option>
            ))}
          </Select>
        </Field>
        {simulating && (
          <Field label="Senaryo" hint="Simüle arayan bu senaryodaki kişiliğe ve amaca göre konuşur; çağrı sonunda değerlendirilir.">
            {scenarios.data?.length === 0 ? (
              <p className="text-sm text-slate-500">
                Henüz senaryo yok.{' '}
                <Link to={`/agents/${agentId}/scenarios`} className="text-indigo-600 hover:underline">
                  Senaryo ekleyin
                </Link>
                .
              </p>
            ) : (
              <Select value={chosenScenario} onChange={(e) => setScenarioId(e.target.value)}>
                {scenarios.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {!simulating && variables.filter((v) => v.name).length > 0 && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-slate-600">Başlangıç değişkenleri</div>
            {variables
              .filter((v) => v.name)
              .map((v) => (
                <div key={v.name} className="flex items-center gap-2">
                  <span className="w-32 shrink-0 truncate font-mono text-xs text-slate-500">{v.name}</span>
                  <Input
                    value={values[v.name] ?? v.default ?? ''}
                    onChange={(e) => setValues({ ...values, [v.name]: e.target.value })}
                  />
                </div>
              ))}
          </div>
        )}
        {call.error && (
          <div className="space-y-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            {call.error}
            <IssueList issues={call.issues.filter((i) => i.severity === 'error')} />
          </div>
        )}
        <Button variant="primary" className="w-full" onClick={start} disabled={simulating && !chosenScenario}>
          <PhoneCall size={16} /> {simulating ? 'Simülasyonu başlat' : 'Çağrıyı başlat'}
        </Button>
      </div>
    )
  }

  return (
    <>
      <div ref={scroller} className="flex-1 overflow-y-auto p-4">
        {timeline}
        {(call.status === 'connecting' || (call.status === 'live' && (thinking || simulating))) && (
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
            <Loader2 size={12} className="animate-spin" />{' '}
            {call.status === 'connecting' ? 'Bağlanıyor…' : thinking ? 'Ajan düşünüyor…' : 'Simüle arayan düşünüyor…'}
          </div>
        )}
        {call.status === 'ended' && simulating && (
          <div className="mt-3 space-y-2 rounded-lg border border-slate-200 bg-white p-3">
            <div className="flex items-center justify-between text-sm font-medium">
              Değerlendirme
              {call.result ? <StatusBadge status={call.result.status} /> : <Loader2 size={14} className="animate-spin text-slate-400" />}
            </div>
            {call.result ? <VerdictCard verdict={call.result.verdict} /> : <p className="text-xs text-slate-400">Hakem değerlendiriyor…</p>}
          </div>
        )}
      </div>
      <div className="space-y-2 border-t border-slate-200 bg-white p-3">
        {call.mic && call.status === 'live' && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant={call.muted ? 'danger' : 'secondary'} onClick={call.toggleMute} title={call.muted ? 'Mikrofonu aç' : 'Sessize al'}>
              {call.muted ? <MicOff size={14} /> : <Mic size={14} />}
            </Button>
            <MicLevel stream={call.mic} muted={call.muted} />
          </div>
        )}
        {call.status === 'ended' ? (
          <Button className="w-full" onClick={call.reset}>
            <RotateCcw size={14} /> Yeni çağrı
          </Button>
        ) : simulating ? (
          <Button className="w-full" variant="danger" onClick={call.hangup} disabled={call.status !== 'live'}>
            <Square size={14} /> Simülasyonu durdur
          </Button>
        ) : (
          <form onSubmit={submit} className="flex gap-2">
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={call.mic ? 'Konuşun veya yazın…' : 'Arayan olarak yazın…'} autoFocus disabled={call.status !== 'live'} />
            <Button variant="primary" disabled={!text.trim() || call.status !== 'live'} aria-label="Gönder">
              <Send size={14} />
            </Button>
            <Button type="button" variant="danger" onClick={call.hangup} title="Çağrıyı bitir" disabled={call.status !== 'live'}>
              <PhoneOff size={14} />
            </Button>
          </form>
        )}
      </div>
    </>
  )
}

function HistoryTab({
  agentId,
  replay,
  setReplay,
  scroller,
  timeline,
}: {
  agentId: string
  replay: SessionDetail | null
  setReplay: (s: SessionDetail | null) => void
  scroller: RefObject<HTMLDivElement | null>
  timeline: ReactNode
}) {
  const sessions = useQuery({
    queryKey: ['sessions', agentId],
    queryFn: () => api<SessionSummary[]>(`/api/agents/${agentId}/sessions`),
  })

  if (replay) {
    return (
      <>
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
          <History size={13} />
          {dateFmt.format(new Date(replay.started_at))} · {replay.flow_version ? `v${replay.flow_version}` : 'Taslak'}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setReplay(null)}>
            Listeye dön
          </Button>
        </div>
        {replay.has_recording && (
          <div className="border-b border-slate-200 bg-white px-3 py-2">
            <RecordingPlayer sessionId={replay.id} />
          </div>
        )}
        <div ref={scroller} className="flex-1 overflow-y-auto p-4">
          {timeline}
        </div>
      </>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {sessions.data?.length === 0 && <p className="p-4 text-sm text-slate-400">Henüz test çağrısı yapılmadı.</p>}
      <ul className="divide-y divide-slate-200">
        {sessions.data?.map((s) => (
          <li key={s.id}>
            <button
              className="w-full px-4 py-2.5 text-left hover:bg-white"
              onClick={async () => setReplay(await api<SessionDetail>(`/api/sessions/${s.id}`))}
            >
              <div className="flex items-center justify-between text-sm">
                <span>{dateFmt.format(new Date(s.started_at))}</span>
                <span className="font-mono text-xs text-slate-500">{s.outcome ?? s.end_reason ?? 'devam ediyor'}</span>
              </div>
              <div className="text-xs text-slate-400">
                {s.mode === 'voice' ? 'Sesli' : 'Yazılı'} · {s.flow_version ? `v${s.flow_version}` : 'Taslak'}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
