import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Button, ErrorText, Field, Input, Modal, Select } from '../components/ui'
import { api } from '../lib/api'
import type { Agent, AgentSettings } from '../lib/types'

type Providers = Record<'llm' | 'stt' | 'tts', Record<string, { label: string; models?: string[]; voices?: string[]; needs_key?: boolean }>>

/** Agent-level voice pipeline settings (STT → LLM → TTS), deliberately not canvas cards. */
export default function SettingsDialog({ agent, readOnly, onClose }: { agent: Agent; readOnly: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ['providers'], queryFn: () => api<Providers>('/api/meta/providers') })
  const [s, setS] = useState<AgentSettings>(agent.settings)

  const save = useMutation({
    mutationFn: () => api<Agent>(`/api/agents/${agent.id}`, { method: 'PATCH', body: { settings: s } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['agent', agent.id], updated)
      onClose()
    },
  })

  const llmProviders = providers.data?.llm ?? {}
  const llmModels = llmProviders[s.llm.provider]?.models ?? []

  return (
    <Modal
      title="Ses ve model ayarları"
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          {!readOnly && (
            <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
              Kaydet
            </Button>
          )}
        </>
      }
    >
      <fieldset disabled={readOnly} className="space-y-6">
        <Section title="Dil modeli (LLM)" note="Konuşmayı yürütür ve akıştaki kararları verir.">
          <Field label="Sağlayıcı" hint={llmProviders[s.llm.provider]?.needs_key ? 'Sunucuda API anahtarı tanımlı olmalı (.env).' : undefined}>
            <Select
              value={s.llm.provider}
              onChange={(e) => {
                const provider = e.target.value as AgentSettings['llm']['provider']
                setS({ ...s, llm: { ...s.llm, provider, model: llmProviders[provider]?.models?.[0] ?? '' } })
              }}
            >
              {Object.entries(llmProviders).map(([key, p]) => (
                <option key={key} value={key}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Model">
            <Input list="llm-models" value={s.llm.model} onChange={(e) => setS({ ...s, llm: { ...s.llm, model: e.target.value } })} />
            <datalist id="llm-models">
              {llmModels.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </Field>
          <Field label="Sıcaklık" hint="Boş: modelin varsayılanı. Düşük değer daha tutarlı yanıt verir.">
            <Input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={s.llm.temperature ?? ''}
              onChange={(e) => setS({ ...s, llm: { ...s.llm, temperature: e.target.value === '' ? null : Number(e.target.value) } })}
            />
          </Field>
        </Section>

        <Section title="Konuşmayı yazıya çevirme (STT)" note="Sesli çağrıda arayanın konuşmasını yazıya çevirir.">
          <Field label="Sağlayıcı">
            <Select value={s.stt.provider} disabled>
              <option value="whisper">Whisper (yerel)</option>
            </Select>
          </Field>
          <Field label="Model">
            <Input list="stt-models" value={s.stt.model} onChange={(e) => setS({ ...s, stt: { ...s.stt, model: e.target.value } })} />
            <datalist id="stt-models">
              {(providers.data?.stt.whisper?.models ?? []).map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </Field>
          <Field label="Dil">
            <Input value={s.stt.language} onChange={(e) => setS({ ...s, stt: { ...s.stt, language: e.target.value } })} />
          </Field>
        </Section>

        <Section title="Yazıyı sese çevirme (TTS)" note="Sesli çağrıda ajanın sesi.">
          <Field label="Sağlayıcı">
            <Select value={s.tts.provider} disabled>
              <option value="piper">Piper (yerel)</option>
            </Select>
          </Field>
          <Field label="Ses">
            <Input list="tts-voices" value={s.tts.voice} onChange={(e) => setS({ ...s, tts: { ...s.tts, voice: e.target.value } })} />
            <datalist id="tts-voices">
              {(providers.data?.tts.piper?.voices ?? []).map((v) => (
                <option key={v} value={v} />
              ))}
            </datalist>
          </Field>
        </Section>

        <Section title="Sıra alma" note="Arayanın sözünün bittiğine ne zaman karar verileceği.">
          <Field
            label="Yöntem"
            hint={s.turn.mode === 'smart' ? 'Bir model, cümlenin tamamlanıp tamamlanmadığına bakar.' : 'Belirlenen süre sessiz kalınca sıra ajana geçer.'}
          >
            <Select value={s.turn.mode} onChange={(e) => setS({ ...s, turn: { ...s.turn, mode: e.target.value as AgentSettings['turn']['mode'] } })}>
              <option value="smart">Akıllı (Smart Turn)</option>
              <option value="silence">Sessizlik süresi</option>
            </Select>
          </Field>
          <Field label="Sessizlik süresi (sn)">
            <Input
              type="number"
              step="0.1"
              min="0.2"
              max="3"
              value={s.turn.vad_stop_secs}
              disabled={s.turn.mode === 'smart'}
              onChange={(e) => setS({ ...s, turn: { ...s.turn, vad_stop_secs: Number(e.target.value) } })}
            />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={s.turn.allow_interruptions}
              onChange={(e) => setS({ ...s, turn: { ...s.turn, allow_interruptions: e.target.checked } })}
            />
            Arayan botun sözünü kesebilir
          </label>
        </Section>
        <ErrorText error={save.error} />
      </fieldset>
    </Modal>
  )
}

function Section({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-2">
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-slate-500">{note}</div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">{children}</div>
    </section>
  )
}
