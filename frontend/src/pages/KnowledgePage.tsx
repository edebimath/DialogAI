import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpenText, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, ErrorText, Field, Input, Modal, Textarea } from '../components/ui'
import KnowledgeTabs from '../knowledge/KnowledgeTabs'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import { useKnowledgeBases } from '../lib/knowledge'
import type { KnowledgeBase } from '../lib/types'

export default function KnowledgePage() {
  const canEdit = hasRole(useAuth((s) => s.user), 'editor')
  const [creating, setCreating] = useState(false)
  const kbs = useKnowledgeBases()

  return (
    <div className="mx-auto max-w-5xl p-6">
      <KnowledgeTabs />
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Bilgi tabanları</h1>
          <p className="text-sm text-slate-500">
            Ajanların soruları cevaplarken dayandığı soru-cevaplar ve dokümanlar. Akışta "Bilgi Tabanı" kartından veya genel ayarlardan bağlanır.
          </p>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus size={16} /> Yeni bilgi tabanı
          </Button>
        )}
      </div>
      <ErrorText error={kbs.error} />
      {kbs.data?.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          Henüz bir bilgi tabanı yok.
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {kbs.data?.map((kb) => (
          <Link
            key={kb.id}
            to={`/knowledge/${kb.id}`}
            className="rounded-xl border border-slate-200 bg-white p-4 hover:border-emerald-300 hover:shadow-sm"
          >
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-emerald-50 p-2 text-emerald-700">
                <BookOpenText size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{kb.name}</div>
                <div className="line-clamp-2 text-sm text-slate-500">{kb.description || 'Açıklama yok'}</div>
              </div>
            </div>
            <div className="mt-3 text-xs text-slate-400">
              {kb.document_count} girdi · {kb.chunk_count} parça
              {kb.ready_count < kb.document_count && ' · işlenen / hatalı dosyalar var'}
            </div>
          </Link>
        ))}
      </div>
      {creating && <CreateDialog onClose={() => setCreating(false)} />}
    </div>
  )
}

function CreateDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => api<KnowledgeBase>('/api/knowledge-bases', { method: 'POST', body: { name, description } }),
    onSuccess: (kb) => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      navigate(`/knowledge/${kb.id}`)
    },
  })
  return (
    <Modal
      title="Yeni bilgi tabanı"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
            Oluştur
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Ad">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ör. Fatura ve ödeme SSS" autoFocus />
        </Field>
        <Field label="Açıklama">
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <ErrorText error={create.error} />
      </div>
    </Modal>
  )
}
