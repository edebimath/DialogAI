import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import { create } from 'zustand'
import type { FlowGraph, GlobalSettings, Issue, NodeContent, NodeKind, Variable } from '../lib/types'
import { CATALOG, OUT, handlesOf, uid } from './catalog'

// React Flow requires node data to be an index-signature record.
export type FlowNodeData = NodeContent & { kind: NodeKind; [key: string]: unknown }
export type FlowNode = Node<FlowNodeData, 'flow'>

interface TraceView {
  active: string | null
  visited: string[]
}

interface EditorState {
  agentId: string | null
  readOnly: boolean
  nodes: FlowNode[]
  edges: Edge[]
  global: GlobalSettings
  variables: Variable[]
  selectedId: string | null
  issues: Issue[]
  /** Bumped on every content change; autosave compares it with savedRevision. */
  revision: number
  savedRevision: number
  trace: TraceView

  load: (agentId: string, graph: FlowGraph, issues: Issue[], readOnly: boolean) => void
  onNodesChange: (changes: NodeChange<FlowNode>[]) => void
  onEdgesChange: (changes: EdgeChange[]) => void
  onConnect: (connection: Connection) => void
  addNode: (kind: NodeKind, position: { x: number; y: number }) => void
  updateNode: (id: string, patch: Partial<NodeContent>) => void
  removeNode: (id: string) => void
  select: (id: string | null) => void
  setGlobal: (patch: Partial<GlobalSettings>) => void
  setVariables: (variables: Variable[]) => void
  setIssues: (issues: Issue[]) => void
  markSaved: (revision: number) => void
  setTrace: (trace: TraceView) => void
  toGraph: () => FlowGraph
}

const EMPTY_TRACE: TraceView = { active: null, visited: [] }

function toFlowNodes(graph: FlowGraph): FlowNode[] {
  return graph.nodes.map(({ id, type, position, ...content }) => ({
    id,
    type: 'flow',
    position,
    deletable: type !== 'start',
    data: { kind: type, ...content },
  }))
}

function toFlowEdges(graph: FlowGraph): Edge[] {
  return graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.source_handle }))
}

function withSelection(nodes: FlowNode[], id: string | null): FlowNode[] {
  return nodes.map((n) => (!!n.selected === (n.id === id) ? n : { ...n, selected: n.id === id }))
}

export const useEditor = create<EditorState>()((set, get) => {
  const touch = () => set((s) => ({ revision: s.revision + 1 }))

  return {
    agentId: null,
    readOnly: false,
    nodes: [],
    edges: [],
    global: { persona: '', rules: '', kb_ids: [], caller_tags: '' },
    variables: [],
    selectedId: null,
    issues: [],
    revision: 0,
    savedRevision: 0,
    trace: EMPTY_TRACE,

    load: (agentId, graph, issues, readOnly) =>
      set({
        agentId,
        readOnly,
        nodes: toFlowNodes(graph),
        edges: toFlowEdges(graph),
        global: graph.global,
        variables: graph.variables,
        issues,
        selectedId: null,
        revision: 0,
        savedRevision: 0,
        trace: EMPTY_TRACE,
      }),

    onNodesChange: (changes) => {
      set({ nodes: applyNodeChanges(changes, get().nodes) })
      const edits = changes.some((c) => c.type === 'remove' || (c.type === 'position' && c.dragging === false))
      if (changes.some((c) => c.type === 'remove')) {
        const ids = new Set(get().nodes.map((n) => n.id))
        set((s) => ({
          edges: s.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
          selectedId: s.selectedId && ids.has(s.selectedId) ? s.selectedId : null,
        }))
      }
      if (edits) touch()
    },

    onEdgesChange: (changes) => {
      set({ edges: applyEdgeChanges(changes, get().edges) })
      if (changes.some((c) => c.type === 'remove')) touch()
    },

    onConnect: (connection) => {
      const handle = connection.sourceHandle ?? OUT
      // One edge per exit: a new connection replaces the old one.
      const kept = get().edges.filter((e) => !(e.source === connection.source && (e.sourceHandle ?? OUT) === handle))
      set({ edges: addEdge({ ...connection, sourceHandle: handle, id: uid('e') }, kept) })
      touch()
    },

    addNode: (kind, position) => {
      const node: FlowNode = {
        id: uid(kind.replace('llm_', '')),
        type: 'flow',
        position,
        data: { kind, ...CATALOG[kind].defaults() },
      }
      set((s) => ({ nodes: [...withSelection(s.nodes, null), { ...node, selected: true }], selectedId: node.id }))
      touch()
    },

    updateNode: (id, patch) => {
      const nodes = get().nodes.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n))
      const node = nodes.find((n) => n.id === id)
      // Drop edges whose exit was removed from the node.
      const handles = node ? new Set(handlesOf(node.data.kind, node.data).map((h) => h.id)) : new Set<string>()
      const edges = get().edges.filter((e) => e.source !== id || handles.has(e.sourceHandle ?? OUT))
      set({ nodes, edges })
      touch()
    },

    removeNode: (id) => {
      set((s) => ({
        nodes: s.nodes.filter((n) => n.id !== id),
        edges: s.edges.filter((e) => e.source !== id && e.target !== id),
        selectedId: s.selectedId === id ? null : s.selectedId,
      }))
      touch()
    },

    // Keep React Flow's own selection in sync, so Delete and styling follow the inspector.
    select: (id) => set((s) => ({ selectedId: id, nodes: withSelection(s.nodes, id) })),
    setGlobal: (patch) => {
      set((s) => ({ global: { ...s.global, ...patch } }))
      touch()
    },
    setVariables: (variables) => {
      set({ variables })
      touch()
    },
    setIssues: (issues) => set({ issues }),
    markSaved: (revision) => set({ savedRevision: revision }),
    setTrace: (trace) => set({ trace }),

    toGraph: () => {
      const { nodes, edges, global, variables } = get()
      return {
        schema_version: 1,
        global,
        variables,
        nodes: nodes.map(({ id, position, data: { kind, ...content } }) => ({
          id,
          type: kind,
          position: { x: Math.round(position.x), y: Math.round(position.y) },
          ...content,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          source_handle: e.sourceHandle ?? OUT,
        })),
      }
    },
  }
})

/** Every variable name a prompt or condition can use: declared variables plus collected fields. */
export function knownVariables(nodes: FlowNode[], variables: Variable[]): string[] {
  const names = new Set(variables.map((v) => v.name))
  for (const n of nodes) {
    for (const f of n.data.fields ?? []) if (f.name) names.add(f.name)
    for (const o of n.data.outputs ?? []) if (o.variable) names.add(o.variable)
  }
  return [...names].filter(Boolean).sort()
}
