import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Button, ErrorText, Field, Input, Modal, Textarea } from '../components/ui'
import { OUTCOMES } from '../editor/catalog'
import { api } from '../lib/api'
import type { Scenario, ScenarioInput } from '../lib/types'

const EMPTY: ScenarioInput = {
  name: '',
  persona: '',
  goal: '',
  success_criteria: '',
  expected_outcome: null,
  variables: {},
  max_turns: 12,
}

export default function ScenarioDialog({
  agentId,
  scenario,
  onClose,
}: {
  agentId: string
  scenario: Scenario | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ScenarioInput>(scenario ? { ...EMPTY, ...scenario } : EMPTY)
  const set = <K extends keyof ScenarioInput>(key: K, value: ScenarioInput[K]) => setForm({ ...form, [key]: value })

  const save = useMutation({
    mutationFn: () =>
      scenario
        ? api<Scenario>(`/api/scenarios/${scenario.id}`, { method: 'PUT', body: form })
        : api<Scenario>(`/api/agents/${agentId}/scenarios`, { method: 'POST', body: form }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scenarios', agentId] })
      onClose()
    },
  })

  return (
    <Modal
      title={scenario ? 'Senaryoyu düzenle' : 'Yeni senaryo'}
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate()}>
            Kaydet
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Senaryo adı">
          <Input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="Ör. Faturasına itiraz eden müşteri" autoFocus />
        </Field>
        <Field label="Arayan kim?" hint="Kişilik, konuşma tarzı ve bildiği bilgiler (ör. müşteri numarası). Simüle arayan bu role girer.">
          <Textarea
            rows={3}
            value={form.persona}
            onChange={(e) => set('persona', e.target.value)}
            placeholder="Mehmet, 38 yaşında, biraz sinirli bir esnaf. Müşteri numarası 771230."
          />
        </Field>
        <Field label="Arayanın amacı" hint="Arayan bu amaca ulaşınca veya ulaşamayacağını anlayınca telefonu kapatır.">
          <Textarea rows={2} value={form.goal} onChange={(e) => set('goal', e.target.value)} placeholder="Faturadaki fazla ücret için kayıt açtırmak." />
        </Field>
        <Field label="Başarı kriteri (LLM hakem)" hint="Konuşma bittikten sonra bir LLM hakem dökümü okuyup bunun karşılanıp karşılanmadığına karar verir. Boş bırakılabilir.">
          <Textarea
            rows={2}
            value={form.success_criteria}
            onChange={(e) => set('success_criteria', e.target.value)}
            placeholder="Ajan talebin fatura ile ilgili olduğunu anladı ve 771230 numarasıyla kayıt açıldığını söyledi."
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Beklenen çağrı sonucu" hint="Akış bu sonuçla (Bitiş kartı) bitmeli. Boş: kontrol edilmez.">
            <Input
              list="scenario-outcomes"
              value={form.expected_outcome ?? ''}
              onChange={(e) => set('expected_outcome', e.target.value || null)}
            />
            <datalist id="scenario-outcomes">
              {OUTCOMES.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          </Field>
          <Field label="En fazla tur" hint="Arayanın en fazla kaç kez konuşacağı.">
            <Input type="number" min={1} max={40} value={form.max_turns} onChange={(e) => set('max_turns', Number(e.target.value) || 12)} />
          </Field>
        </div>
        <ErrorText error={save.error} />
      </div>
    </Modal>
  )
}
