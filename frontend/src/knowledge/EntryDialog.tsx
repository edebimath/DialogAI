import { useMutation } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import TagInput from '../components/TagInput'
import { Button, ErrorText, Field, Modal, Textarea } from '../components/ui'
import { api } from '../lib/api'
import type { KBDocument } from '../lib/types'
import { TAG_RULE } from './tags'

/** Add or edit a question-answer entry. */
export default function EntryDialog({
  kbId,
  entry,
  canEdit,
  onClose,
  onSaved,
}: {
  kbId: string
  entry: KBDocument | null
  canEdit: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [question, setQuestion] = useState(entry?.question ?? '')
  const [answer, setAnswer] = useState(entry?.answer ?? '')
  const [tags, setTags] = useState<string[]>(entry?.tags ?? [])

  const save = useMutation({
    mutationFn: () => {
      const body = { question: question.trim(), answer: answer.trim(), tags }
      return entry
        ? api(`/api/knowledge-bases/${kbId}/documents/${entry.id}`, { method: 'PATCH', body })
        : api(`/api/knowledge-bases/${kbId}/qa`, { method: 'POST', body })
    },
    onSuccess: () => {
      onSaved()
      onClose()
    },
  })
  const remove = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}/documents/${entry!.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      onSaved()
      onClose()
    },
  })
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <Modal
      wide
      title={entry ? 'Soru-cevap' : 'Yeni soru-cevap'}
      onClose={onClose}
      footer={
        canEdit && (
          <>
            {entry &&
              (confirmDelete ? (
                <Button variant="danger" className="mr-auto" onClick={() => remove.mutate()} disabled={remove.isPending}>
                  Silmeyi onayla
                </Button>
              ) : (
                <Button variant="ghost" className="mr-auto text-rose-600" onClick={() => setConfirmDelete(true)}>
                  <Trash2 size={14} /> Sil
                </Button>
              ))}
            <Button onClick={onClose}>Vazgeç</Button>
            <Button variant="primary" disabled={!question.trim() || !answer.trim() || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
            </Button>
          </>
        )
      }
    >
      <fieldset disabled={!canEdit} className="space-y-4">
        <Field label="Soru" hint="Arayanın soracağı şekilde yazın; benzer sorular da bu girdiyi bulur.">
          <Textarea rows={2} value={question} autoFocus={!entry} onChange={(e) => setQuestion(e.target.value)} placeholder="Ör. Faturamı ne zamana kadar ödemeliyim?" />
        </Field>
        <Field label="Cevap" hint="Ajan bu metne dayanarak cevap verir; kısa ve net tutun.">
          <Textarea rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Ör. Son ödeme günü her ayın 15'idir." />
        </Field>
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">Kimlere gösterilsin?</div>
          <TagInput value={tags} onChange={setTags} placeholder="Etiketsiz: herkese. Seçin veya yeni etiket yazın" />
          <p className="text-xs text-slate-400">{TAG_RULE}</p>
        </div>
        <ErrorText error={save.error ?? remove.error} />
      </fieldset>
    </Modal>
  )
}
