import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { KnowledgeBase, Tag, TagColor } from './types'

export function useKnowledgeBases() {
  return useQuery({ queryKey: ['knowledge-bases'], queryFn: () => api<KnowledgeBase[]>('/api/knowledge-bases') })
}

/** The tags defined on the tags screen. */
export function useTags() {
  return useQuery({ queryKey: ['tags'], queryFn: () => api<Tag[]>('/api/tags') })
}

/** Chip classes per tag color: [normal, selected]. Full class names so Tailwind keeps them. */
export const TAG_TONES: Record<TagColor, [string, string]> = {
  violet: ['bg-violet-50 text-violet-700 ring-violet-100', 'bg-violet-600 text-white ring-violet-600'],
  indigo: ['bg-indigo-50 text-indigo-700 ring-indigo-100', 'bg-indigo-600 text-white ring-indigo-600'],
  sky: ['bg-sky-50 text-sky-700 ring-sky-100', 'bg-sky-600 text-white ring-sky-600'],
  teal: ['bg-teal-50 text-teal-700 ring-teal-100', 'bg-teal-600 text-white ring-teal-600'],
  emerald: ['bg-emerald-50 text-emerald-700 ring-emerald-100', 'bg-emerald-600 text-white ring-emerald-600'],
  amber: ['bg-amber-50 text-amber-800 ring-amber-100', 'bg-amber-500 text-white ring-amber-500'],
  orange: ['bg-orange-50 text-orange-700 ring-orange-100', 'bg-orange-600 text-white ring-orange-600'],
  rose: ['bg-rose-50 text-rose-700 ring-rose-100', 'bg-rose-600 text-white ring-rose-600'],
  slate: ['bg-slate-100 text-slate-700 ring-slate-200', 'bg-slate-700 text-white ring-slate-700'],
}
export const TAG_SWATCH: Record<TagColor, string> = {
  violet: 'bg-violet-500',
  indigo: 'bg-indigo-500',
  sky: 'bg-sky-500',
  teal: 'bg-teal-500',
  emerald: 'bg-emerald-500',
  amber: 'bg-amber-400',
  orange: 'bg-orange-500',
  rose: 'bg-rose-500',
  slate: 'bg-slate-500',
}

/** Same rule as normalize_tag() in backend/app/kb/tags.py. */
export function normalizeTag(tag: string): string {
  return tag.replace(/\s+/g, ' ').trim().replaceAll('I', 'ı').replaceAll('İ', 'i').toLocaleLowerCase('tr-TR').slice(0, 64)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
