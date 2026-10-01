import { useMutation } from '@tanstack/react-query'
import clsx from 'clsx'
import { FileText, MessageSquareText, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import TagInput, { TagChip } from '../components/TagInput'
import { Button, ErrorText, Input } from '../components/ui'
import { api } from '../lib/api'
import type { SearchResult } from '../lib/types'

const MIN_SCORE = 0.45

/** Shows what the agent would find for a question, optionally as a caller with given tags. */
export default function SearchTester({ kbId }: { kbId: string }) {
  const [query, setQuery] = useState('')
  const [asCaller, setAsCaller] = useState(false)
  const [tags, setTags] = useState<string[]>([])
  const search = useMutation({
    mutationFn: (q: string) =>
      api<SearchResult>(`/api/knowledge-bases/${kbId}/search`, {
        method: 'POST',
        body: { query: q, top_k: 5, ...(asCaller ? { tags } : {}) },
      }),
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    if (query.trim()) search.mutate(query.trim())
  }

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <div>
        <h2 className="font-medium">Deneme araması</h2>
        <p className="text-xs text-slate-500">
          Ajanın bir soru için neyi bulacağını görün. {MIN_SCORE.toFixed(2)} altındaki sonuçlar çağrıda "bulunamadı" sayılır.
        </p>
      </div>
      <form onSubmit={submit} className="space-y-2">
        <div className="flex gap-2">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ör. İndirim var mı?" />
          <Button variant="primary" disabled={!query.trim() || search.isPending}>
            <Search size={14} /> Ara
          </Button>
        </div>
        <div className="flex gap-1 rounded-md bg-slate-100 p-0.5 text-xs">
          {[
            [false, 'Tüm girdiler'],
            [true, 'Bir arayan gibi'],
          ].map(([value, label]) => (
            <button
              key={String(value)}
              type="button"
              onClick={() => setAsCaller(value as boolean)}
              className={clsx('flex-1 rounded px-2 py-1', asCaller === value ? 'bg-white font-medium shadow-sm' : 'text-slate-500')}
            >
              {label as string}
            </button>
          ))}
        </div>
        {asCaller && (
          <div className="space-y-1">
            <TagInput value={tags} onChange={setTags} allowCreate={false} placeholder="Arayanın etiketleri (boş: tanınmayan arayan)" />
            <p className="text-xs text-slate-400">Etiketsiz girdiler ve bu etiketlerden birini taşıyan girdiler aranır.</p>
          </div>
        )}
      </form>
      <ErrorText error={search.error} />
      {search.data && (
        <div className="space-y-2">
          <div className="text-xs text-slate-400">{search.data.ms} ms</div>
          {search.data.hits.length === 0 && <p className="text-sm text-slate-500">Sonuç yok.</p>}
          {search.data.hits.map((h) => (
            <div key={h.chunk_id} className={clsx('rounded-lg border p-3 text-sm', h.score >= MIN_SCORE ? 'border-slate-200' : 'border-dashed border-slate-200 opacity-60')}>
              <div className="mb-1 flex items-start gap-1.5 text-xs text-slate-500">
                {h.kind === 'qa' ? <MessageSquareText size={12} className="mt-0.5 shrink-0" /> : <FileText size={12} className="mt-0.5 shrink-0" />}
                <span className="min-w-0 flex-1 truncate">
                  {h.document}
                  {h.page && `, sayfa ${h.page}`}
                </span>
                <span className="font-mono">{h.score.toFixed(2)}</span>
              </div>
              <p className="line-clamp-4 whitespace-pre-wrap text-slate-700">{h.text}</p>
              {h.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {h.tags.map((t) => (
                    <TagChip key={t} tag={t} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
