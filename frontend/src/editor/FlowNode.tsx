import { Handle, Position, useUpdateNodeInternals, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'
import { AlertTriangle } from 'lucide-react'
import { memo, useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useKnowledgeBases } from '../lib/knowledge'
import { CATALOG, handlesOf } from './catalog'
import { useEditor, type FlowNode as FlowNodeType } from './store'

function FlowNode({ id, data, selected }: NodeProps<FlowNodeType>) {
  const meta = CATALOG[data.kind]
  const Icon = meta.icon
  const handles = handlesOf(data.kind, data)
  const branching = handles.length > 1 || (handles.length === 1 && handles[0].label !== null)

  const issues = useEditor(useShallow((s) => s.issues.filter((i) => i.node_id === id)))
  const isActive = useEditor((s) => s.trace.active === id)
  const wasVisited = useEditor((s) => s.trace.visited.includes(id))
  const errors = issues.filter((i) => i.severity === 'error').length

  // React Flow caches handle positions; refresh them when exits are added or removed.
  const updateInternals = useUpdateNodeInternals()
  const handleKey = handles.map((h) => h.id).join('|')
  useEffect(() => updateInternals(id), [id, handleKey, updateInternals])

  return (
    <div
      className={clsx(
        'w-60 rounded-xl border bg-white shadow-sm transition-shadow',
        errors ? 'border-rose-300' : wasVisited ? 'border-emerald-300' : 'border-slate-200',
        selected && 'ring-2 ring-indigo-400',
        isActive && 'shadow-lg ring-4 ring-emerald-400/60',
      )}
    >
      {data.kind !== 'start' && <Handle type="target" position={Position.Left} />}

      <div className="flex items-center gap-2 px-3 py-2">
        <span className={clsx('rounded-md p-1', meta.tone)}>
          <Icon size={14} />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{data.label || meta.title}</span>
        {issues.length > 0 && (
          <span title={issues.map((i) => i.message).join('\n')}>
            <AlertTriangle size={14} className={errors ? 'text-rose-500' : 'text-amber-500'} />
          </span>
        )}
      </div>

      <Summary data={data} />

      {branching ? (
        <div className="border-t border-slate-100 py-1">
          {handles.map((h) => (
            <div key={h.id} className="relative px-3 py-1 text-right text-xs text-slate-500">
              <span className="block truncate pr-2">{h.label}</span>
              <Handle type="source" position={Position.Right} id={h.id} />
            </div>
          ))}
        </div>
      ) : (
        handles.length === 1 && <Handle type="source" position={Position.Right} id={handles[0].id} />
      )}
    </div>
  )
}

function Summary({ data }: { data: FlowNodeType['data'] }) {
  const muted = 'px-3 pb-2 text-xs text-slate-500'
  switch (data.kind) {
    case 'start':
      return <div className={muted}>Çağrı burada başlar.</div>
    case 'say':
      return <div className={clsx(muted, 'line-clamp-3 italic')}>{data.text ? `“${data.text}”` : 'Metin girilmedi'}</div>
    case 'llm_task':
    case 'llm_router':
      return data.prompt ? <div className={clsx(muted, 'line-clamp-2')}>{data.prompt}</div> : null
    case 'collect':
      return (
        <div className="flex flex-wrap gap-1 px-3 pb-2">
          {(data.fields ?? []).map((f, i) => (
            <span key={i} className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[11px] text-amber-800">
              {f.name || '?'}
            </span>
          ))}
        </div>
      )
    case 'kb_answer':
      return <KBSummary ids={data.kb_ids ?? []} />
    case 'http_request':
      return (
        <div className="space-y-1 px-3 pb-2">
          <div className="flex min-w-0 items-center gap-1.5 text-[11px]">
            <span className="shrink-0 rounded bg-orange-50 px-1 font-mono font-medium text-orange-700">{data.method ?? 'GET'}</span>
            <span className="truncate font-mono text-slate-500" title={data.url}>
              {data.url || 'Adres girilmedi'}
            </span>
          </div>
          {(data.outputs ?? []).length > 0 && (
            <div className="flex flex-wrap gap-1">
              {(data.outputs ?? []).map((o, i) => (
                <span key={i} className="rounded bg-orange-50 px-1.5 py-0.5 font-mono text-[11px] text-orange-800">
                  {o.variable || '?'}
                </span>
              ))}
            </div>
          )}
        </div>
      )
    case 'transfer':
      return (
        <div className={muted}>
          <div className="line-clamp-2 italic">{data.text ? `“${data.text}”` : 'Varsayılan aktarma metni'}</div>
          <span className="mt-1 inline-block rounded bg-fuchsia-50 px-1.5 py-0.5 text-[11px] text-fuchsia-700">
            → {data.target || 'Müşteri temsilcisi'}
          </span>
        </div>
      )
    case 'end':
      return (
        <div className={muted}>
          <div className="line-clamp-2 italic">{data.text ? `“${data.text}”` : 'LLM vedalaşır'}</div>
          <span className="mt-1 inline-block rounded bg-rose-50 px-1.5 py-0.5 font-mono text-[11px] text-rose-700">
            {data.outcome}
          </span>
        </div>
      )
    default:
      return null
  }
}

function KBSummary({ ids }: { ids: string[] }) {
  const kbs = useKnowledgeBases()
  const names = ids.map((id) => kbs.data?.find((k) => k.id === id)?.name ?? '?')
  if (!names.length) return <div className="px-3 pb-2 text-xs text-rose-500">Bilgi tabanı seçilmedi</div>
  return (
    <div className="flex flex-wrap gap-1 px-3 pb-2">
      {names.map((n, i) => (
        <span key={i} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-800">
          {n}
        </span>
      ))}
    </div>
  )
}

export default memo(FlowNode)
