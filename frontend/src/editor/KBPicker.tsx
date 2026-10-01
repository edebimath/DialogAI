import { Link } from 'react-router-dom'
import { useKnowledgeBases } from '../lib/knowledge'

/** Checkbox list of knowledge bases; ids that no longer exist are shown so they can be removed. */
export default function KBPicker({ value, onChange }: { value: string[]; onChange: (ids: string[]) => void }) {
  const kbs = useKnowledgeBases()
  const known = new Set(kbs.data?.map((k) => k.id))
  const missing = value.filter((id) => kbs.data && !known.has(id))

  if (kbs.data?.length === 0)
    return (
      <p className="text-xs text-slate-500">
        Henüz bilgi tabanı yok.{' '}
        <Link to="/knowledge" className="text-indigo-600 hover:underline">
          Bilgi tabanı oluşturun
        </Link>
        .
      </p>
    )

  const toggle = (id: string, on: boolean) => onChange(on ? [...value, id] : value.filter((v) => v !== id))
  return (
    <div className="space-y-1">
      {kbs.data?.map((kb) => (
        <label key={kb.id} className="flex items-center gap-2 rounded-md px-1 py-0.5 text-sm hover:bg-slate-50">
          <input type="checkbox" checked={value.includes(kb.id)} onChange={(e) => toggle(kb.id, e.target.checked)} />
          <span className="min-w-0 flex-1 truncate">{kb.name}</span>
          <span className="text-xs text-slate-400">{kb.chunk_count} parça</span>
        </label>
      ))}
      {missing.map((id) => (
        <label key={id} className="flex items-center gap-2 px-1 py-0.5 text-sm text-rose-600">
          <input type="checkbox" checked onChange={() => toggle(id, false)} />
          Silinmiş bilgi tabanı (kaldırmak için işareti kaldırın)
        </label>
      ))}
    </div>
  )
}
