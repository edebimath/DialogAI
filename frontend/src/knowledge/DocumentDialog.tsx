import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Loader2, Pencil, RotateCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import TagInput from '../components/TagInput'
import { Button, ErrorText, Modal, Textarea } from '../components/ui'
import { api } from '../lib/api'
import { formatBytes } from '../lib/knowledge'
import type { KBChunk, KBDocument } from '../lib/types'
import { TAG_RULE } from './tags'

/** An uploaded file: who it is for, and the chunks the agent actually reads, editable one by one. */
export default function DocumentDialog({
  kbId,
  doc,
  canEdit,
  onClose,
  onChanged,
}: {
  kbId: string
  doc: KBDocument
  canEdit: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const queryClient = useQueryClient()
  const chunksKey = ['kb-chunks', doc.id]
  const chunks = useQuery({
    queryKey: chunksKey,
    queryFn: () => api<KBChunk[]>(`/api/knowledge-bases/${kbId}/documents/${doc.id}/chunks`),
  })
  const [tags, setTags] = useState(doc.tags)
  const tagsChanged = tags.join('|') !== doc.tags.join('|')
  const changed = () => {
    queryClient.invalidateQueries({ queryKey: chunksKey })
    onChanged()
  }

  const saveTags = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}/documents/${doc.id}`, { method: 'PATCH', body: { tags } }),
    onSuccess: onChanged,
  })
  const reindex = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}/documents/${doc.id}/reindex`, { method: 'POST' }),
    onSuccess: () => {
      onChanged()
      onClose()
    },
  })
  const [confirmReindex, setConfirmReindex] = useState(false)

  return (
    <Modal wide title={doc.filename} onClose={onClose}>
      <div className="space-y-5">
        <div className="text-xs text-slate-500">
          {formatBytes(doc.size)} · {doc.chunk_count} parça
          {doc.edited_chunks > 0 && <span className="text-amber-700"> · {doc.edited_chunks} parça elle düzenlendi</span>}
        </div>

        <fieldset disabled={!canEdit} className="space-y-1">
          <div className="text-xs font-medium text-slate-600">Kimlere gösterilsin?</div>
          <div className="flex gap-2">
            <div className="min-w-0 flex-1">
              <TagInput value={tags} onChange={setTags} placeholder="Etiketsiz: herkese" />
            </div>
            {canEdit && (
              <Button variant="primary" disabled={!tagsChanged || saveTags.isPending} onClick={() => saveTags.mutate()}>
                Kaydet
              </Button>
            )}
          </div>
          <p className="text-xs text-slate-400">Etiketler dokümanın tüm parçalarına uygulanır. {TAG_RULE}</p>
          <ErrorText error={saveTags.error} />
        </fieldset>

        <div className="space-y-2">
          <div className="flex items-end justify-between">
            <div>
              <div className="text-sm font-medium">Parçalar</div>
              <div className="text-xs text-slate-400">Ajan dokümanı bu parçalar halinde arar ve okur. Hatalı bir parçayı düzeltebilir veya silebilirsiniz.</div>
            </div>
            {canEdit &&
              (confirmReindex ? (
                <Button size="sm" variant="danger" onClick={() => reindex.mutate()}>
                  Düzenlemeleri silip yeniden işle
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="ghost"
                  title="Dosyayı baştan parçalara ayır"
                  onClick={() => (doc.edited_chunks > 0 ? setConfirmReindex(true) : reindex.mutate())}
                >
                  <RotateCw size={13} /> Yeniden işle
                </Button>
              ))}
          </div>
          <ErrorText error={chunks.error ?? reindex.error} />
          {chunks.isPending && <Loader2 className="mx-auto animate-spin text-slate-400" size={18} />}
          {chunks.data?.map((c) => (
            <ChunkRow key={c.id} kbId={kbId} chunk={c} canEdit={canEdit} onChanged={changed} />
          ))}
        </div>
      </div>
    </Modal>
  )
}

function ChunkRow({ kbId, chunk, canEdit, onChanged }: { kbId: string; chunk: KBChunk; canEdit: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(chunk.text)
  const save = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}/chunks/${chunk.id}`, { method: 'PATCH', body: { text: text.trim() } }),
    onSuccess: () => {
      setEditing(false)
      onChanged()
    },
  })
  const remove = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}/chunks/${chunk.id}`, { method: 'DELETE' }),
    onSuccess: onChanged,
  })

  return (
    <div className={clsx('group rounded-lg border p-3', chunk.edited ? 'border-amber-200 bg-amber-50/30' : 'border-slate-200')}>
      <div className="mb-1 flex items-center gap-2 text-xs text-slate-400">
        <span className="font-mono">#{chunk.ordinal + 1}</span>
        {chunk.page && <span>sayfa {chunk.page}</span>}
        {chunk.edited && <span className="rounded bg-amber-100 px-1.5 text-amber-800">elle düzenlendi</span>}
        {canEdit && !editing && (
          <span className="ml-auto flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button title="Düzenle" className="rounded p-1 hover:bg-slate-100 hover:text-slate-700" onClick={() => setEditing(true)}>
              <Pencil size={13} />
            </button>
            <button title="Parçayı sil" className="rounded p-1 hover:bg-rose-50 hover:text-rose-600" onClick={() => remove.mutate()}>
              <Trash2 size={13} />
            </button>
          </span>
        )}
      </div>
      {editing ? (
        <div className="space-y-2">
          <Textarea rows={Math.min(14, Math.max(4, Math.ceil(text.length / 80)))} value={text} autoFocus onChange={(e) => setText(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              onClick={() => {
                setText(chunk.text)
                setEditing(false)
              }}
            >
              Vazgeç
            </Button>
            <Button size="sm" variant="primary" disabled={!text.trim() || text === chunk.text || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
            </Button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap text-sm text-slate-700">{chunk.text}</p>
      )}
      <ErrorText error={save.error ?? remove.error} />
    </div>
  )
}
