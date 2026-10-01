// Mirrors backend/app/flows/schema.py and app/api/schemas.py.

export type Role = 'admin' | 'editor' | 'viewer'

export interface User {
  id: string
  email: string
  name: string
  role: Role
  is_active: boolean
}

export type NodeKind =
  | 'start'
  | 'say'
  | 'llm_task'
  | 'collect'
  | 'llm_router'
  | 'condition'
  | 'kb_answer'
  | 'http_request'
  | 'transfer'
  | 'end'

export interface Exit {
  id: string
  description: string
}

export interface CollectField {
  name: string
  description: string
  type: 'string' | 'number' | 'boolean'
  required: boolean
}

export type Operator = 'eq' | 'neq' | 'contains' | 'gt' | 'lt' | 'exists' | 'not_exists'

export interface Rule {
  id: string
  variable: string
  operator: Operator
  value: string
}

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface Header {
  name: string
  value: string
}

/** Stores one value of the JSON response in a variable; path is dotted, e.g. "data.slots.0". */
export interface HttpOutput {
  variable: string
  path: string
}

/** Everything a node can carry besides id/type/position; each kind uses a subset. */
export interface NodeContent {
  label?: string | null
  text?: string | null
  prompt?: string
  exits?: Exit[]
  routes?: Exit[]
  fields?: CollectField[]
  rules?: Rule[]
  outcome?: string
  kb_ids?: string[]
  top_k?: number
  fallback?: boolean
  method?: HttpMethod
  url?: string
  headers?: Header[]
  body?: string
  timeout?: number
  outputs?: HttpOutput[]
  target?: string
  summary?: boolean
}

export interface GraphNode extends NodeContent {
  id: string
  type: NodeKind
  position: { x: number; y: number }
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  source_handle: string
}

export interface Variable {
  name: string
  description: string
  default: string | null
}

export interface GlobalSettings {
  persona: string
  rules: string
  kb_ids: string[]
  /** The caller's tags for knowledge-base searches, e.g. "{{ musteri_tipi }}"; empty = no filtering. */
  caller_tags?: string
}

export interface FlowGraph {
  schema_version: number
  global: GlobalSettings
  variables: Variable[]
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Issue {
  severity: 'error' | 'warning'
  code: string
  message: string
  node_id: string | null
  edge_id: string | null
}

export interface FlowOut {
  version: number
  graph: FlowGraph
  issues: Issue[]
  updated_at: string | null
}

export interface AgentSettings {
  llm: { provider: 'ollama' | 'google'; model: string; temperature: number | null }
  stt: { provider: 'whisper'; model: string; language: string }
  tts: { provider: 'piper'; voice: string }
  turn: { mode: 'smart' | 'silence'; vad_stop_secs: number; allow_interruptions: boolean }
}

export interface Agent {
  id: string
  name: string
  description: string
  settings: AgentSettings
  created_at: string
  updated_at: string
  published_version: number | null
}

export interface Version {
  version: number
  note: string
  created_at: string
}

export interface Template {
  key: string
  name: string
  description: string
}

export type TraceEventType =
  | 'session_started'
  | 'node_entered'
  | 'say'
  | 'user_message'
  | 'bot_message'
  | 'function_call'
  | 'variables_set'
  | 'condition_evaluated'
  | 'kb_search'
  | 'http_request'
  | 'transfer'
  | 'llm_ttfb'
  | 'stt_time'
  | 'tts_ttfb'
  | 'voice_latency'
  | 'interrupted'
  | 'caller_hangup'
  | 'empty_reply'
  | 'error'
  | 'session_ended'

export interface TraceEvent {
  seq: number
  ts: number
  type: TraceEventType
  node_id: string | null
  data: Record<string, unknown>
}

export interface SessionSummary {
  id: string
  agent_id: string
  flow_version: number
  mode: string
  started_at: string
  ended_at: string | null
  outcome: string | null
  end_reason: string | null
}

export interface SessionDetail extends SessionSummary {
  graph: FlowGraph
  events: TraceEvent[]
  has_recording: boolean
}

export type CallMode = 'text' | 'voice' | 'simulation'

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  document_count: number
  ready_count: number
  chunk_count: number
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

/** An entry of a knowledge base: an uploaded file or a question-answer pair typed in. */
export interface KBDocument {
  id: string
  kind: 'file' | 'qa'
  filename: string
  question: string | null
  answer: string | null
  tags: string[]
  size: number
  status: DocumentStatus
  error: string | null
  chunk_count: number
  edited_chunks: number
  created_at: string
  updated_at: string | null
}

export type TagColor = 'violet' | 'indigo' | 'sky' | 'teal' | 'emerald' | 'amber' | 'orange' | 'rose' | 'slate'

/** A tag defined on the tags screen; entries can only carry defined tags. */
export interface Tag {
  id: string
  name: string
  description: string
  color: TagColor
  created_at: string
  entry_count: number
}

export interface KBChunk {
  id: number
  ordinal: number
  page: number | null
  text: string
  edited: boolean
}

export interface KnowledgeBaseDetail extends KnowledgeBase {
  documents: KBDocument[]
}

export interface SearchHit {
  chunk_id: number
  kb_id: string
  document_id: string
  document: string
  kind: 'file' | 'qa'
  tags: string[]
  page: number | null
  score: number
  text: string
}

export interface SearchResult {
  query: string
  hits: SearchHit[]
  ms: number
}

export interface VerdictCheck {
  name: string
  passed: boolean
  detail: string
}

export interface Verdict {
  passed: boolean
  checks: VerdictCheck[]
  judge?: { passed: boolean; reason: string } | null
  caller?: { success: boolean; reason: string } | null
  error?: string
}

export type ResultStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'cancelled'

export interface ScenarioResult {
  id: string
  run_id: string | null
  scenario_id: string | null
  scenario_name: string
  ordinal: number
  session_id: string | null
  status: ResultStatus
  outcome: string | null
  end_reason: string | null
  turns: number
  duration: number | null
  verdict: Verdict | Record<string, never>
  created_at: string
}

export interface Scenario {
  id: string
  agent_id: string
  name: string
  persona: string
  goal: string
  success_criteria: string
  expected_outcome: string | null
  variables: Record<string, string>
  max_turns: number
  created_at: string
  updated_at: string
  last_result: ScenarioResult | null
}

export type ScenarioInput = Pick<Scenario, 'name' | 'persona' | 'goal' | 'success_criteria' | 'expected_outcome' | 'variables' | 'max_turns'>

export interface ScenarioRun {
  id: string
  agent_id: string
  flow_version: number
  status: 'queued' | 'running' | 'done' | 'cancelled'
  created_at: string
  finished_at: string | null
  total: number
  passed: number
  failed: number
  pending: number
}

export interface ScenarioRunDetail extends ScenarioRun {
  results: ScenarioResult[]
}
