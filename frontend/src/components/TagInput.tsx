import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import { normalizeTag, TAG_TONES, useTags } from '../lib/knowledge'
import type { Tag } from '../lib/types'

/**
 * Picks defined tags. Typing filters the list; a name that isn't defined yet can be created
 * right here (editors), the same as on the tags screen.
 */
export default function TagInput({
  value,
  onChange,
  placeholder = 'Etiket seçin…',
  autoFocus,
  allowCreate = true,
}: {
  value: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  autoFocus?: boolean
  allowCreate?: boolean
}) {
  const queryClient = useQueryClient()
  const tags = useTags()
  const user = useAuth((s) => s.user)
  const canCreate = allowCreate && hasRole(user, 'editor')
  const [draft, setDraft] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)

  const needle = normalizeTag(draft)
  const options = (tags.data ?? []).filter((t) => !value.includes(t.name) && t.name.includes(needle))
  const exists = (tags.data ?? []).some((t) => t.name === needle)
  const offerCreate = canCreate && !!needle && !exists
  const count = options.length + (offerCreate ? 1 : 0)

  const create = useMutation({
    mutationFn: (name: string) => api<Tag>('/api/tags', { method: 'POST', body: { name } }),
    onSuccess: (tag) => {
      queryClient.invalidateQueries({ queryKey: ['tags'] })
      pick(tag.name)
    },
  })

  function pick(name: string) {
    if (!value.includes(name)) onChange([...value, name])
    setDraft('')
    setActive(0)
  }
  function choose(index: number) {
    if (index < options.length) pick(options[index].name)
    else if (offerCreate) create.mutate(needle)
  }

  return (
    <div className="relative">
      <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-md border border-slate-300 bg-white px-1.5 py-1 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
        {value.map((tag) => (
          <TagChip key={tag} tag={tag} onRemove={() => onChange(value.filter((t) => t !== tag))} />
        ))}
        <input
          value={draft}
          autoFocus={autoFocus}
          placeholder={value.length ? '' : placeholder}
          aria-label="Etiket ara veya oluştur"
          className="min-w-24 flex-1 bg-transparent px-1 py-0.5 text-sm outline-none placeholder:text-slate-400"
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onChange={(e) => {
            setDraft(e.target.value)
            setActive(0)
            setOpen(true)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((i) => Math.min(i + 1, count - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((i) => Math.max(i - 1, 0))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              // An exact name wins over the highlighted row.
              const exact = options.findIndex((o) => o.name === needle)
              if (count) choose(exact >= 0 ? exact : active)
            } else if (e.key === 'Escape') {
              setOpen(false)
            } else if (e.key === 'Backspace' && !draft && value.length) {
              onChange(value.slice(0, -1))
            }
          }}
        />
      </div>
      {open && (count > 0 || (tags.data && !tags.data.length)) && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg">
          {options.map((t, i) => (
            <li
              key={t.id}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(i)
              }}
              onMouseEnter={() => setActive(i)}
              className={clsx('flex cursor-pointer items-center gap-2 px-2.5 py-1.5', i === active && 'bg-slate-100')}
            >
              <TagChip tag={t.name} />
              {t.description && <span className="truncate text-xs text-slate-400">{t.description}</span>}
            </li>
          ))}
          {offerCreate && (
            <li
              onMouseDown={(e) => {
                e.preventDefault()
                choose(options.length)
              }}
              onMouseEnter={() => setActive(options.length)}
              className={clsx('flex cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-indigo-700', active === options.length && 'bg-slate-100')}
            >
              <Plus size={13} /> “{needle}” etiketini oluştur
            </li>
          )}
          {tags.data && !tags.data.length && !offerCreate && (
            <li className="px-2.5 py-1.5 text-xs text-slate-400">Henüz etiket yok. Etiketler ekranından oluşturun.</li>
          )}
        </ul>
      )}
      {create.error && <p className="mt-1 text-xs text-rose-600">{create.error.message}</p>}
    </div>
  )
}

/** A tag in its defined color; an undefined name (e.g. a caller tag in a test) shows gray. */
export function TagChip({ tag, onRemove, onClick, active }: { tag: string; onRemove?: () => void; onClick?: () => void; active?: boolean }) {
  const tags = useTags()
  const color = tags.data?.find((t) => t.name === tag)?.color ?? 'slate'
  return (
    <span
      onClick={onClick}
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ring-1',
        TAG_TONES[color][active ? 1 : 0],
        onClick && 'cursor-pointer hover:brightness-95',
      )}
    >
      {tag}
      {onRemove && (
        <button type="button" className="opacity-60 hover:opacity-100" onClick={onRemove} aria-label={`${tag} etiketini kaldır`}>
          <X size={11} />
        </button>
      )}
    </span>
  )
}
