import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button, ErrorText, Field, Input, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { FlowOut, Version } from '../lib/types'

const dateFmt = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium', timeStyle: 'short' })

export default function VersionsDialog({
  agentId,
  canEdit,
  hasErrors,
  beforePublish,
  onRestored,
  onClose,
}: {
  agentId: string
  canEdit: boolean
  hasErrors: boolean
  beforePublish: () => Promise<void>
  onRestored: (flow: FlowOut) => void
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const versions = useQuery({ queryKey: ['versions', agentId], queryFn: () => api<Version[]>(`/api/agents/${agentId}/versions`) })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['versions', agentId] })
    queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
  }
  const publish = useMutation({
    mutationFn: async () => {
      await beforePublish()
      return api<Version>(`/api/agents/${agentId}/publish`, { method: 'POST', body: { note } })
    },
    onSuccess: () => {
      setNote('')
      refresh()
    },
  })
  const restore = useMutation({
    mutationFn: (version: number) => api<FlowOut>(`/api/agents/${agentId}/versions/${version}/restore`, { method: 'POST' }),
    onSuccess: (flow) => {
      onRestored(flow)
      onClose()
    },
  })

  return (
    <Modal title="Yayınlama ve sürümler" onClose={onClose}>
      <div className="space-y-5">
        {canEdit && (
          <div className="space-y-2 rounded-lg bg-slate-50 p-3">
            <Field label="Sürüm notu" hint="Taslak, numaralı ve değişmez bir sürüm olarak kaydedilir.">
              <Input value={note} placeholder="Ör. Fatura dalı eklendi" onChange={(e) => setNote(e.target.value)} />
            </Field>
            {hasErrors && <p className="text-xs text-rose-600">Akışta hatalar var; yayınlamadan önce düzeltin.</p>}
            <Button variant="primary" disabled={hasErrors || publish.isPending} onClick={() => publish.mutate()}>
              Taslağı yayınla
            </Button>
            <ErrorText error={publish.error} />
          </div>
        )}

        <div>
          <div className="mb-2 text-xs font-medium text-slate-600">Yayınlanmış sürümler</div>
          {versions.data?.length === 0 && <p className="text-sm text-slate-400">Henüz yayınlanmış sürüm yok.</p>}
          <ul className="divide-y divide-slate-100">
            {versions.data?.map((v) => (
              <li key={v.version} className="flex items-center gap-3 py-2 text-sm">
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-mono text-xs text-emerald-700">v{v.version}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate">{v.note || '—'}</div>
                  <div className="text-xs text-slate-400">{dateFmt.format(new Date(v.created_at))}</div>
                </div>
                {canEdit && (
                  <Button
                    size="sm"
                    onClick={() => {
                      if (window.confirm(`Taslak, v${v.version} ile değiştirilsin mi?`)) restore.mutate(v.version)
                    }}
                  >
                    Taslağa yükle
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <ErrorText error={restore.error} />
        </div>
      </div>
    </Modal>
  )
}
