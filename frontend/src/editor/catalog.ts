import { BookOpenText, Flag, GitBranch, Globe, Headset, ListChecks, MessageSquareQuote, Play, Sparkles, Split, type LucideIcon } from 'lucide-react'
import type { NodeContent, NodeKind, Operator } from '../lib/types'

export interface NodeKindMeta {
  title: string
  description: string
  icon: LucideIcon
  /** Tailwind classes for the icon chip and palette accent. */
  tone: string
  defaults: () => NodeContent
}

export const uid = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 8)}`

export const CATALOG: Record<NodeKind, NodeKindMeta> = {
  start: {
    title: 'Başlangıç',
    description: 'Çağrının başladığı yer.',
    icon: Play,
    tone: 'bg-slate-100 text-slate-600',
    defaults: () => ({}),
  },
  say: {
    title: 'Söylem',
    description: 'Sabit bir metni okur, LLM kullanmadan sonraki adıma geçer.',
    icon: MessageSquareQuote,
    tone: 'bg-sky-100 text-sky-700',
    defaults: () => ({ text: '' }),
  },
  llm_task: {
    title: 'LLM Görevi',
    description: 'Serbest konuşma adımı; LLM işi bitince bir çıkış seçer.',
    icon: Sparkles,
    tone: 'bg-violet-100 text-violet-700',
    defaults: () => ({ prompt: '', exits: [{ id: uid('x'), description: 'Görev tamamlandı' }] }),
  },
  collect: {
    title: 'Bilgi Toplama',
    description: 'Arayandan bilgileri alır ve değişkenlere yazar.',
    icon: ListChecks,
    tone: 'bg-amber-100 text-amber-700',
    defaults: () => ({ prompt: '', fields: [{ name: '', description: '', type: 'string', required: true }] }),
  },
  llm_router: {
    title: 'Akıllı Yönlendirici',
    description: 'Arayanın niyetini anlar ve uygun dala yönlendirir.',
    icon: Split,
    tone: 'bg-indigo-100 text-indigo-700',
    defaults: () => ({ prompt: '', routes: [{ id: uid('r'), description: '' }] }),
  },
  condition: {
    title: 'Koşul',
    description: 'Değişkenlere göre kural tabanlı dallanır, LLM kullanmaz.',
    icon: GitBranch,
    tone: 'bg-teal-100 text-teal-700',
    defaults: () => ({ rules: [{ id: uid('k'), variable: '', operator: 'eq', value: '' }] }),
  },
  kb_answer: {
    title: 'Bilgi Tabanı',
    description: 'Soruları seçilen bilgi tabanlarındaki dokümanlardan cevaplar.',
    icon: BookOpenText,
    tone: 'bg-emerald-100 text-emerald-700',
    defaults: () => ({
      prompt: '',
      kb_ids: [],
      top_k: 4,
      exits: [{ id: uid('x'), description: 'Arayanın başka sorusu yok' }],
    }),
  },
  http_request: {
    title: 'HTTP Aracı',
    description: 'Bir dış servise istek atar, cevaptaki değerleri değişkenlere yazar. LLM kullanmaz.',
    icon: Globe,
    tone: 'bg-orange-100 text-orange-700',
    defaults: () => ({ method: 'GET', url: '', headers: [], body: '', timeout: 10, outputs: [] }),
  },
  transfer: {
    title: 'Temsilciye Aktar',
    description: 'Çağrıyı bir müşteri temsilcisine devreder; temsilci için özet hazırlar.',
    icon: Headset,
    tone: 'bg-fuchsia-100 text-fuchsia-700',
    defaults: () => ({ target: '', text: 'Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın.', summary: true }),
  },
  end: {
    title: 'Bitiş',
    description: 'Çağrıyı bir sonuçla bitirir.',
    icon: Flag,
    tone: 'bg-rose-100 text-rose-700',
    defaults: () => ({ text: '', outcome: 'completed' }),
  },
}

export const PALETTE_KINDS: NodeKind[] = ['say', 'llm_task', 'collect', 'llm_router', 'condition', 'kb_answer', 'http_request', 'transfer', 'end']

export const OUT = 'out'
export const ELSE = 'else'
export const FALLBACK = 'fallback'
export const ERROR = 'error'

export interface HandleSpec {
  id: string
  label: string | null
}

/** Source handles a node exposes; must match exit_handles() in backend/app/flows/schema.py. */
export function handlesOf(kind: NodeKind, content: NodeContent): HandleSpec[] {
  switch (kind) {
    case 'collect':
      return content.fallback
        ? [
            { id: OUT, label: 'Bilgiler alındı' },
            { id: FALLBACK, label: 'Bilgi verilemedi' },
          ]
        : [{ id: OUT, label: null }]
    case 'start':
    case 'say':
      return [{ id: OUT, label: null }]
    case 'http_request':
      return [
        { id: OUT, label: 'Başarılı' },
        { id: ERROR, label: 'Hata' },
      ]
    case 'llm_task':
    case 'kb_answer':
      return (content.exits ?? []).map((e) => ({ id: e.id, label: e.description || 'Çıkış' }))
    case 'llm_router':
      return (content.routes ?? []).map((r) => ({ id: r.id, label: r.description || 'Seçenek' }))
    case 'condition':
      return [
        ...(content.rules ?? []).map((r) => ({ id: r.id, label: describeRule(r.variable, r.operator, r.value) })),
        { id: ELSE, label: 'Diğer durumlar' },
      ]
    case 'end':
    case 'transfer':
      return []
  }
}

export const OPERATORS: { value: Operator; label: string; needsValue: boolean }[] = [
  { value: 'eq', label: 'eşittir', needsValue: true },
  { value: 'neq', label: 'eşit değildir', needsValue: true },
  { value: 'contains', label: 'içerir', needsValue: true },
  { value: 'gt', label: 'büyüktür', needsValue: true },
  { value: 'lt', label: 'küçüktür', needsValue: true },
  { value: 'exists', label: 'dolu', needsValue: false },
  { value: 'not_exists', label: 'boş', needsValue: false },
]

export function describeRule(variable: string, operator: Operator, value: string): string {
  const op = OPERATORS.find((o) => o.value === operator)
  if (!variable) return 'Kural'
  return op?.needsValue ? `${variable} ${op.label} "${value}"` : `${variable} ${op?.label ?? operator}`
}

export const OUTCOMES = ['completed', 'ticket_created', 'appointment_booked', 'resolved', 'transferred', 'abandoned']

export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const
