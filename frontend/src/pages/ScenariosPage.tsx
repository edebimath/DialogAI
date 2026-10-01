import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, ChevronDown, ChevronRight, Loader2, Pencil, Play, PlayCircle, Plus, Square, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button, ErrorText, Select } from '../components/ui'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import type { Agent, Scenario, ScenarioResult, ScenarioRun, ScenarioRunDetail, SessionDetail, Version } from '../lib/types'
import ScenarioDialog from '../scenarios/ScenarioDialog'
import { StatusBadge, VerdictCard } from '../scenarios/Verdict'
import Timeline, { type NodeInfo } from '../test/Timeline'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' })
const END_REASON: Record<string, string> = {
  flow_ended: 'akış bitti',
  caller_hangup: 'arayan kapattı',
  max_turns: 'tur sınırı',
  loop: 'döngü',
  silence: 'ajan sessiz',
  timeout: 'süre doldu',
  user_hangup: 'durduruldu',
  error: 'hata',
}

export default function ScenariosPage() {
  const { agentId = '' } = useParams()
  const canEdit = hasRole(useAuth((s) => s.user), 'editor')
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Scenario | 'new' | null>(null)
  const [version, setVersion] = useState(0)
  const [selectedRun, setSelectedRun] = useState<string | null>(null)

  const agent = useQuery({ queryKey: ['agent', agentId], queryFn: () => api<Agent>(`/api/agents/${agentId}`) })
  const versions = useQuery({ queryKey: ['versions', agentId], queryFn: () => api<Version[]>(`/api/agents/${agentId}/versions`) })
  const scenarios = useQuery({
    queryKey: ['scenarios', agentId],
    queryFn: () => api<Scenario[]>(`/api/agents/${agentId}/scenarios`),
  })
  const runs = useQuery({
    queryKey: ['scenario-runs', agentId],
    queryFn: () => api<ScenarioRun[]>(`/api/agents/${agentId}/scenario-runs`),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'queued' || r.status === 'running') ? 2000 : false),
  })
  const activeRun = selectedRun ?? runs.data?.[0]?.id ?? null

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['scenario-runs', agentId] })
    queryClient.invalidateQueries({ queryKey: ['scenarios', agentId] })
  }
  const startRun = useMutation({
    mutationFn: (ids: string[] | null) =>
      api<ScenarioRun>(`/api/agents/${agentId}/scenario-runs`, { method: 'POST', body: { version, scenario_ids: ids } }),
    onSuccess: (run) => {
      setSelectedRun(run.id)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/scenarios/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={`/agents/${agentId}`} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="Akışa dön">
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">Senaryolar · {agent.data?.name}</h1>
          <p className="text-sm text-slate-500">
            Simüle arayanlar akışı uçtan uca test eder; her çağrı kurallar ve bir LLM hakem tarafından değerlendirilir.
          </p>
        </div>
        {canEdit && (
          <>
            <div className="w-32">
              <Select value={version} onChange={(e) => setVersion(Number(e.target.value))} title="Test edilecek akış">
                <option value={0}>Taslak</option>
                {versions.data?.map((v) => (
                  <option key={v.version} value={v.version}>
                    v{v.version}
                  </option>
                ))}
              </Select>
            </div>
            <Button onClick={() => setEditing('new')}>
              <Plus size={15} /> Yeni senaryo
            </Button>
            <Button variant="primary" disabled={!scenarios.data?.length || startRun.isPending} onClick={() => startRun.mutate(null)}>
              <PlayCircle size={15} /> Tümünü çalıştır
            </Button>
          </>
        )}
      </div>
      <ErrorText error={scenarios.error ?? runs.error ?? startRun.error ?? remove.error} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <section className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Senaryolar ({scenarios.data?.length ?? 0})</h2>
          {scenarios.data?.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">Henüz senaryo yok.</div>
          )}
          {scenarios.data?.map((s) => (
            <div key={s.id} className="group rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{s.name}</span>
                    {s.last_result && <StatusBadge status={s.last_result.status} />}
                  </div>
                  <p className="line-clamp-2 text-sm text-slate-500">{s.goal || 'Amaç yazılmadı'}</p>
                  <div className="mt-1 flex flex-wrap gap-1 text-[11px]">
                    {s.expected_outcome && <span className="rounded bg-rose-50 px-1.5 py-0.5 font-mono text-rose-700">{s.expected_outcome}</span>}
                    {s.success_criteria && <span className="rounded bg-violet-50 px-1.5 py-0.5 text-violet-700">hakem kriteri</span>}
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">en fazla {s.max_turns} tur</span>
                  </div>
                </div>
                {canEdit && (
                  <div className="flex shrink-0 gap-1">
                    <button title="Yalnızca bunu çalıştır" className="rounded p-1 text-slate-400 hover:bg-indigo-50 hover:text-indigo-600" onClick={() => startRun.mutate([s.id])}>
                      <Play size={14} />
                    </button>
                    <button title="Düzenle" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" onClick={() => setEditing(s)}>
                      <Pencil size={14} />
                    </button>
                    <button
                      title="Sil"
                      className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                      onClick={() => window.confirm(`"${s.name}" silinsin mi?`) && remove.mutate(s.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Koşular</h2>
            {runs.data && runs.data.length > 0 && (
              <div className="w-80 max-w-full">
              <Select className="text-xs" value={activeRun ?? ''} onChange={(e) => setSelectedRun(e.target.value)}>
                {runs.data.map((r) => (
                  <option key={r.id} value={r.id}>
                    {dateFmt.format(new Date(r.created_at))} · {r.flow_version ? `v${r.flow_version}` : 'Taslak'} · {r.passed}/{r.total} geçti
                    {r.status === 'running' || r.status === 'queued' ? ' · çalışıyor' : ''}
                  </option>
                ))}
              </Select>
              </div>
            )}
          </div>
          {!runs.data?.length && (
            <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
              Henüz koşu yok. "Tümünü çalıştır" ile başlayın.
            </div>
          )}
          {activeRun && <RunDetail agentId={agentId} runId={activeRun} canEdit={canEdit} />}
        </section>
      </div>

      {editing && <ScenarioDialog agentId={agentId} scenario={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function RunDetail({ agentId, runId, canEdit }: { agentId: string; runId: string; canEdit: boolean }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState<string | null>(null)
  const run = useQuery({
    queryKey: ['scenario-run', runId],
    queryFn: () => api<ScenarioRunDetail>(`/api/scenario-runs/${runId}`),
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 1500 : false),
  })
  // When the run finishes, the scenario cards' last-result badges and the run list change too.
  const finished = run.data && !['queued', 'running'].includes(run.data.status)
  useEffect(() => {
    if (finished) {
      queryClient.invalidateQueries({ queryKey: ['scenarios', agentId] })
      queryClient.invalidateQueries({ queryKey: ['scenario-runs', agentId] })
    }
  }, [finished, agentId, queryClient])
  const cancel = useMutation({
    mutationFn: () => api(`/api/scenario-runs/${runId}/cancel`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scenario-run', runId] }),
  })
  if (!run.data) return <Loader2 className="animate-spin text-slate-300" />
  const r = run.data
  const done = r.total - r.pending
  const active = r.status === 'queued' || r.status === 'running'

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        <div className="flex-1">
          <div className="text-sm font-medium">
            {r.passed}/{r.total} geçti
            {r.failed > 0 && <span className="text-rose-600"> · {r.failed} kaldı</span>}
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="flex h-full">
              <div className="bg-emerald-500" style={{ width: `${(r.passed / r.total) * 100}%` }} />
              <div className="bg-rose-400" style={{ width: `${(r.failed / r.total) * 100}%` }} />
              <div className="bg-slate-300" style={{ width: `${((done - r.passed - r.failed) / r.total) * 100}%` }} />
            </div>
          </div>
        </div>
        {active && canEdit && (
          <Button size="sm" variant="danger" onClick={() => cancel.mutate()}>
            <Square size={12} /> Durdur
          </Button>
        )}
      </div>
      <ul className="divide-y divide-slate-100">
        {r.results.map((res) => (
          <li key={res.id}>
            <button
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-slate-50"
              onClick={() => setOpen(open === res.id ? null : res.id)}
              disabled={!res.session_id}
            >
              {open === res.id ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
              <span className="min-w-0 flex-1 truncate">{res.scenario_name}</span>
              <span className="hidden text-xs text-slate-400 sm:inline">
                {res.turns ? `${res.turns} tur` : ''}
                {res.duration ? ` · ${res.duration} sn` : ''}
                {res.end_reason ? ` · ${END_REASON[res.end_reason] ?? res.end_reason}` : ''}
              </span>
              <StatusBadge status={res.status} />
            </button>
            {open === res.id && <ResultDetail result={res} />}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ResultDetail({ result }: { result: ScenarioResult }) {
  const [details, setDetails] = useState(false)
  const session = useQuery({
    queryKey: ['session', result.session_id, result.status],
    queryFn: () => api<SessionDetail>(`/api/sessions/${result.session_id}`),
    enabled: !!result.session_id,
    refetchInterval: result.status === 'running' ? 1500 : false,
  })
  const nodes = useMemo(() => {
    const info: Record<string, NodeInfo> = {}
    for (const n of session.data?.graph.nodes ?? []) info[n.id] = { label: n.label ?? '', kind: n.type }
    return info
  }, [session.data])

  return (
    <div className={clsx('grid gap-4 border-t border-slate-100 bg-slate-50 px-4 py-3 md:grid-cols-2')}>
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Değerlendirme</div>
        {result.status === 'running' ? <p className="text-sm text-slate-500">Çağrı sürüyor…</p> : <VerdictCard verdict={result.verdict} />}
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
          Konuşma
          <label className="flex items-center gap-1 font-normal normal-case tracking-normal">
            <input type="checkbox" checked={details} onChange={(e) => setDetails(e.target.checked)} /> sistem olayları
          </label>
        </div>
        <div className="max-h-96 overflow-y-auto pr-1">
          {session.data ? <Timeline events={session.data.events} nodes={nodes} details={details} onNodeClick={() => {}} /> : <Loader2 className="animate-spin text-slate-300" />}
        </div>
      </div>
    </div>
  )
}
