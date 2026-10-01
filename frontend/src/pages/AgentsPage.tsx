import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bot, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, ErrorText, Field, Input, Modal, Textarea } from '../components/ui'
import { api } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import type { Agent, Template } from '../lib/types'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' })

export default function AgentsPage() {
  const user = useAuth((s) => s.user)
  const canEdit = hasRole(user, 'editor')
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const agents = useQuery({ queryKey: ['agents'], queryFn: () => api<Agent[]>('/api/agents') })

  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/agents/${id}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Ajanlar</h1>
          <p className="text-sm text-slate-500">Her ajan bir çağrı akışı ve ses/model ayarlarından oluşur.</p>
        </div>
        {canEdit && (
          <Button variant="primary" onClick={() => setCreating(true)}>
            <Plus size={16} /> Yeni ajan
          </Button>
        )}
      </div>

      <ErrorText error={agents.error} />
      {agents.data?.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          Henüz bir ajan yok. {canEdit && 'Hazır bir şablonla başlayabilirsiniz.'}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.data?.map((agent) => (
          <div key={agent.id} className="group relative rounded-xl border border-slate-200 bg-white p-4 hover:border-indigo-300 hover:shadow-sm">
            <Link to={`/agents/${agent.id}`} className="absolute inset-0" aria-label={agent.name} />
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
                <Bot size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{agent.name}</div>
                <div className="line-clamp-2 text-sm text-slate-500">{agent.description || 'Açıklama yok'}</div>
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
              <span>{dateFmt.format(new Date(agent.updated_at))}</span>
              <span
                className={clsx(
                  'rounded px-1.5 py-0.5',
                  agent.published_version ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500',
                )}
              >
                {agent.published_version ? `v${agent.published_version} yayında` : 'Taslak'}
              </span>
            </div>
            {canEdit && (
              <button
                className="absolute right-2 top-2 z-10 hidden rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 group-hover:block"
                title="Sil"
                onClick={() => {
                  if (window.confirm(`"${agent.name}" silinsin mi? Akış ve test geçmişi de silinir.`)) remove.mutate(agent.id)
                }}
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        ))}
      </div>

      {creating && <CreateAgentDialog onClose={() => setCreating(false)} />}
    </div>
  )
}

function CreateAgentDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const templates = useQuery({ queryKey: ['templates'], queryFn: () => api<Template[]>('/api/meta/templates') })
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [template, setTemplate] = useState('ariza_fatura')

  const create = useMutation({
    mutationFn: () => api<Agent>('/api/agents', { method: 'POST', body: { name, description, template } }),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      navigate(`/agents/${agent.id}`)
    },
  })

  return (
    <Modal
      title="Yeni ajan"
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
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ör. Fatura destek hattı" autoFocus />
        </Field>
        <Field label="Açıklama">
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="space-y-1">
          <span className="text-xs font-medium text-slate-600">Başlangıç şablonu</span>
          <div className="grid gap-2">
            {templates.data?.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTemplate(t.key)}
                className={clsx(
                  'rounded-lg border p-3 text-left',
                  template === t.key ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-slate-300',
                )}
              >
                <div className="text-sm font-medium">{t.name}</div>
                <div className="text-xs text-slate-500">{t.description}</div>
              </button>
            ))}
          </div>
        </div>
        <ErrorText error={create.error} />
      </div>
    </Modal>
  )
}
