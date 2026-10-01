import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, Pencil, Plus, Tags, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { TagChip } from '../components/TagInput'
import { Button, ErrorText, Field, Input, Modal, Textarea } from '../components/ui'
import KnowledgeTabs from '../knowledge/KnowledgeTabs'
import { TAG_RULE } from '../knowledge/tags'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import { normalizeTag, TAG_SWATCH, useTags } from '../lib/knowledge'
import type { Tag, TagColor } from '../lib/types'

const COLORS = Object.keys(TAG_SWATCH) as TagColor[]

export default function TagsPage() {
  const canEdit = hasRole(useAuth((s) => s.user), 'editor')
  const tags = useTags()
  const [editing, setEditing] = useState<Tag | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Tag | null>(null)

  return (
    <div className="mx-auto max-w-5xl p-6">
      <KnowledgeTabs />
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Etiketler</h1>
          <p className="max-w-2xl text-sm text-slate-500">
            Bilgi tabanı girdilerinin hangi arayanlara gösterileceğini belirleyen kategoriler (ör. VIP, kurumsal, ön ödemeli). {TAG_RULE}
          </p>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setEditing('new')}>
            <Plus size={16} /> Yeni etiket
          </Button>
        )}
      </div>
      <ErrorText error={tags.error} />

      {tags.data?.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          <Tags className="mx-auto mb-2 text-slate-300" size={24} />
          Henüz etiket yok. Bir etiket oluşturup bilgi tabanı girdilerine verin; akışta "Arayan etiketleri" ile eşleşen arayanlar bu girdileri görür.
        </div>
      )}

      {!!tags.data?.length && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Etiket</th>
                <th className="px-4 py-2 font-medium">Açıklama</th>
                <th className="px-4 py-2 font-medium">Kullanıldığı girdi</th>
                <th className="w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {tags.data.map((t) => (
                <tr key={t.id} className="group">
                  <td className="px-4 py-2.5">
                    <TagChip tag={t.name} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-600">{t.description || <span className="text-slate-300">—</span>}</td>
                  <td className="px-4 py-2.5 text-slate-600">{t.entry_count}</td>
                  <td className="px-2 py-2.5 text-right">
                    {canEdit && (
                      <div className="flex justify-end gap-1">
                        <button title="Düzenle" className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" onClick={() => setEditing(t)}>
                          <Pencil size={14} />
                        </button>
                        <button title="Sil" className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600" onClick={() => setDeleting(t)}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && <TagDialog tag={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {deleting && <DeleteDialog tag={deleting} onClose={() => setDeleting(null)} />}
    </div>
  )
}

function useRefreshTags() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ['tags'] })
    // Renames and deletions rewrite entries too.
    queryClient.invalidateQueries({ queryKey: ['knowledge-base'] })
  }
}

function TagDialog({ tag, onClose }: { tag: Tag | null; onClose: () => void }) {
  const refresh = useRefreshTags()
  const [name, setName] = useState(tag?.name ?? '')
  const [description, setDescription] = useState(tag?.description ?? '')
  const [color, setColor] = useState<TagColor>(tag?.color ?? 'violet')
  const normalized = normalizeTag(name)
  const renaming = tag && normalized && normalized !== tag.name

  const save = useMutation({
    mutationFn: () => {
      const body = { name, description, color }
      return tag ? api(`/api/tags/${tag.id}`, { method: 'PATCH', body }) : api('/api/tags', { method: 'POST', body })
    },
    onSuccess: () => {
      refresh()
      onClose()
    },
  })

  return (
    <Modal
      title={tag ? 'Etiketi düzenle' : 'Yeni etiket'}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" disabled={!normalized || normalized.includes(',') || save.isPending} onClick={() => save.mutate()}>
            {tag ? 'Kaydet' : 'Oluştur'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Ad" hint={normalized ? <>Kaydedilecek ad: <TagChip tag={normalized} /></> : 'Küçük harfe çevrilir; virgül kullanılamaz.'}>
          <Input value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="Ör. VIP müşteri" />
        </Field>
        {renaming && tag.entry_count > 0 && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Yeni ad bu etiketi taşıyan {tag.entry_count} girdiye de yansır. Akışlarda "Arayan etiketleri" bu adı üreten değişkenler de güncellenmeli.
          </p>
        )}
        <Field label="Açıklama (isteğe bağlı)" hint="Etiketi seçerken görünür; kimleri kapsadığını yazın.">
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">Renk</div>
          <div className="flex gap-2">
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={c}
                onClick={() => setColor(c)}
                className={clsx('flex h-7 w-7 items-center justify-center rounded-full text-white', TAG_SWATCH[c], color === c && 'ring-2 ring-slate-400 ring-offset-2')}
              >
                {color === c && <Check size={14} />}
              </button>
            ))}
          </div>
        </div>
        <ErrorText error={save.error} />
      </div>
    </Modal>
  )
}

function DeleteDialog({ tag, onClose }: { tag: Tag; onClose: () => void }) {
  const refresh = useRefreshTags()
  const remove = useMutation({
    mutationFn: () => api(`/api/tags/${tag.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      refresh()
      onClose()
    },
  })
  return (
    <Modal
      title="Etiketi sil"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate()}>
            Sil
          </Button>
        </>
      }
    >
      <div className="space-y-2 text-sm text-slate-600">
        <p>
          <TagChip tag={tag.name} /> etiketi silinecek.
        </p>
        {tag.entry_count > 0 && (
          <p>
            Etiket {tag.entry_count} girdiden kaldırılır. Başka etiketi olmayan girdiler bundan sonra <b>her arayana</b> gösterilir.
          </p>
        )}
        <ErrorText error={remove.error} />
      </div>
    </Modal>
  )
}
