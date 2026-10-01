import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
} from '@xyflow/react'
import clsx from 'clsx'
import { AlertTriangle, ArrowLeft, Check, CloudUpload, FlaskConical, Loader2, PhoneCall, Settings2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { Button, ErrorText } from '../components/ui'
import { CATALOG } from '../editor/catalog'
import FlowNode from '../editor/FlowNode'
import GlobalPanel from '../editor/GlobalPanel'
import Inspector from '../editor/Inspector'
import Palette, { DRAG_MIME } from '../editor/Palette'
import SettingsDialog from '../editor/SettingsDialog'
import { useEditor } from '../editor/store'
import VersionsDialog from '../editor/VersionsDialog'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import type { Agent, FlowOut, NodeKind } from '../lib/types'
import TestDrawer from '../test/TestDrawer'

const nodeTypes = { flow: FlowNode }
const AUTOSAVE_MS = 700

export default function EditorPage() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  )
}

function Editor() {
  const { agentId = '' } = useParams()
  const canEdit = hasRole(useAuth((s) => s.user), 'editor')
  const agent = useQuery({ queryKey: ['agent', agentId], queryFn: () => api<Agent>(`/api/agents/${agentId}`) })
  const flow = useQuery({ queryKey: ['flow', agentId], queryFn: () => api<FlowOut>(`/api/agents/${agentId}/flow`), staleTime: Infinity })

  const editor = useEditor(
    useShallow((s) => ({
      load: s.load,
      nodes: s.nodes,
      edges: s.edges,
      onNodesChange: s.onNodesChange,
      onEdgesChange: s.onEdgesChange,
      onConnect: s.onConnect,
      addNode: s.addNode,
      select: s.select,
      selectedId: s.selectedId,
      issues: s.issues,
      revision: s.revision,
      savedRevision: s.savedRevision,
      visited: s.trace.visited,
    })),
  )
  const { screenToFlowPosition, setCenter, getNode, fitView } = useReactFlow()
  const [dialog, setDialog] = useState<'settings' | 'versions' | null>(null)
  const [testing, setTesting] = useState(false)

  // Load the draft into the editor store once per agent, then frame it once the nodes are measured.
  useEffect(() => {
    if (!flow.data) return
    useEditor.getState().load(agentId, flow.data.graph, flow.data.issues, !canEdit)
    const timer = setTimeout(() => fitView({ padding: 0.15, maxZoom: 1 }), 60)
    return () => clearTimeout(timer)
  }, [flow.data, agentId, canEdit, fitView])

  // --- Autosave -----------------------------------------------------------------
  const save = useMutation({
    mutationFn: async () => {
      const { revision, toGraph } = useEditor.getState()
      const out = await api<FlowOut>(`/api/agents/${agentId}/flow`, { method: 'PUT', body: { graph: toGraph() } })
      return { out, revision }
    },
    onSuccess: ({ out, revision }) => {
      const state = useEditor.getState()
      state.setIssues(out.issues)
      state.markSaved(Math.max(state.savedRevision, revision))
    },
  })
  const saveNow = save.mutateAsync // stable across renders

  const dirty = editor.revision !== editor.savedRevision
  useEffect(() => {
    if (!canEdit || !dirty) return
    const timer = setTimeout(() => saveNow().catch(() => {}), AUTOSAVE_MS)
    return () => clearTimeout(timer)
  }, [editor.revision, dirty, canEdit, saveNow])

  const ensureSaved = useCallback(async () => {
    const { revision, savedRevision } = useEditor.getState()
    if (canEdit && revision !== savedRevision) await saveNow()
  }, [canEdit, saveNow])

  // --- Canvas interactions -----------------------------------------------------
  const addAt = useCallback(
    (kind: NodeKind, position?: { x: number; y: number }) => {
      const center = screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 })
      editor.addNode(kind, position ?? { x: center.x - 120, y: center.y - 40 })
    },
    [editor, screenToFlowPosition],
  )

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      const kind = e.dataTransfer.getData(DRAG_MIME) as NodeKind
      if (!kind || !CATALOG[kind]) return
      const p = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      addAt(kind, { x: p.x - 120, y: p.y - 30 })
    },
    [addAt, screenToFlowPosition],
  )

  const focusNode = useCallback(
    (id: string) => {
      const node = getNode(id)
      if (node) setCenter(node.position.x + 120, node.position.y + 60, { zoom: 1, duration: 400 })
    },
    [getNode, setCenter],
  )

  // Edges the test call went along: both ends visited.
  const edges: Edge[] = useMemo(() => {
    const visited = new Set(editor.visited)
    return editor.edges.map((e) => ({ ...e, className: visited.has(e.source) && visited.has(e.target) ? 'traversed' : undefined }))
  }, [editor.edges, editor.visited])

  const selected = editor.nodes.find((n) => n.id === editor.selectedId)
  const errors = editor.issues.filter((i) => i.severity === 'error').length
  const warnings = editor.issues.length - errors

  if (agent.error || flow.error) return <div className="p-6"><ErrorText error={agent.error ?? flow.error} /></div>
  if (!agent.data || !flow.data) return <div className="flex h-full items-center justify-center text-slate-400"><Loader2 className="animate-spin" /></div>

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-12 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-3">
        <Link to="/" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" title="Ajanlara dön">
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{agent.data.name}</div>
          <div className="text-[11px] text-slate-400">
            Taslak{agent.data.published_version ? ` · v${agent.data.published_version} yayında` : ''}
            {!canEdit && ' · salt okunur'}
          </div>
        </div>

        <SaveState saving={save.isPending} dirty={dirty} failed={save.isError} />
        <button
          onClick={() => editor.select(null)}
          className={clsx(
            'flex items-center gap-1 rounded px-2 py-1 text-xs',
            errors ? 'bg-rose-50 text-rose-700' : warnings ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700',
          )}
          title="Sorunları göster"
        >
          {errors || warnings ? <AlertTriangle size={12} /> : <Check size={12} />}
          {errors ? `${errors} hata` : warnings ? `${warnings} uyarı` : 'Akış geçerli'}
        </button>

        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => setDialog('settings')}>
            <Settings2 size={15} /> Ses & Model
          </Button>
          <Link
            to={`/agents/${agentId}/scenarios`}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <FlaskConical size={15} /> Senaryolar
          </Link>
          <Button onClick={() => setDialog('versions')}>
            <CloudUpload size={15} /> Yayınla
          </Button>
          <Button variant="primary" onClick={() => setTesting(true)}>
            <PhoneCall size={15} /> Test et
          </Button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1">
        {canEdit && <Palette onAdd={(kind) => addAt(kind)} />}
        <div className="relative min-w-0 flex-1" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
          <ReactFlow
            nodes={editor.nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={editor.onNodesChange}
            onEdgesChange={editor.onEdgesChange}
            onConnect={editor.onConnect}
            onNodeClick={(_, node) => editor.select(node.id)}
            onPaneClick={() => editor.select(null)}
            nodesDraggable={canEdit}
            nodesConnectable={canEdit}
            elementsSelectable
            deleteKeyCode={canEdit ? ['Delete', 'Backspace'] : null}
            defaultEdgeOptions={{ type: 'smoothstep' }}
          >
            <Background gap={20} color="#e2e8f0" />
            <Controls showInteractive={false} />
            <MiniMap pannable zoomable className="!bg-white" />
          </ReactFlow>
        </div>
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-4">
          {selected ? <Inspector key={selected.id} node={selected} /> : <GlobalPanel />}
        </aside>

        {testing && <TestDrawer agentId={agentId} ensureSaved={ensureSaved} onClose={() => setTesting(false)} />}
      </div>

      {dialog === 'settings' && <SettingsDialog agent={agent.data} readOnly={!canEdit} onClose={() => setDialog(null)} />}
      {dialog === 'versions' && (
        <VersionsDialog
          agentId={agentId}
          canEdit={canEdit}
          hasErrors={errors > 0}
          beforePublish={ensureSaved}
          onRestored={(restored) => useEditor.getState().load(agentId, restored.graph, restored.issues, !canEdit)}
          onClose={() => setDialog(null)}
        />
      )}
      <FocusOnSelect focus={focusNode} />
    </div>
  )
}

/** Centers the canvas on a node selected from outside it (test timeline, issue list, palette). */
function FocusOnSelect({ focus }: { focus: (id: string) => void }) {
  const selectedId = useEditor((s) => s.selectedId)
  const last = useRef<string | null>(null)
  useEffect(() => {
    // Only pan when selection came from outside the canvas (timeline, issue list).
    if (selectedId && selectedId !== last.current && !document.activeElement?.closest('.react-flow')) focus(selectedId)
    last.current = selectedId
  }, [selectedId, focus])
  return null
}

function SaveState({ saving, dirty, failed }: { saving: boolean; dirty: boolean; failed: boolean }) {
  const text = failed ? 'Kaydedilemedi' : saving ? 'Kaydediliyor…' : dirty ? 'Değişiklikler kaydedilecek' : 'Kaydedildi'
  return <span className={clsx('text-xs', failed ? 'text-rose-600' : 'text-slate-400')}>{text}</span>
}
