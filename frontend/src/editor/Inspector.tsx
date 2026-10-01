import clsx from 'clsx'
import { AlertTriangle, Plus, Trash2, X } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'
import { Button, Field, Input, Select, Textarea } from '../components/ui'
import type { CollectField, Exit, Header, HttpMethod, HttpOutput, Issue, NodeContent, Rule } from '../lib/types'
import { CATALOG, HTTP_METHODS, OPERATORS, OUTCOMES, uid } from './catalog'
import KBPicker from './KBPicker'
import { knownVariables, useEditor, type FlowNode } from './store'

const VAR_HINT = 'Değişkenleri {{ degisken_adi }} şeklinde kullanabilirsiniz.'

export default function Inspector({ node }: { node: FlowNode }) {
  const { updateNode, removeNode, readOnly } = useEditor(
    useShallow((s) => ({ updateNode: s.updateNode, removeNode: s.removeNode, readOnly: s.readOnly })),
  )
  const issues = useEditor(useShallow((s) => s.issues.filter((i) => i.node_id === node.id)))
  const meta = CATALOG[node.data.kind]
  const Icon = meta.icon
  const data = node.data
  const update = (patch: Partial<NodeContent>) => updateNode(node.id, patch)

  return (
    <fieldset disabled={readOnly} className="space-y-4">
      <div className="flex items-start gap-2">
        <span className={clsx('rounded-md p-1.5', meta.tone)}>
          <Icon size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-medium">{meta.title}</div>
          <div className="text-xs text-slate-500">{meta.description}</div>
        </div>
        {data.kind !== 'start' && !readOnly && (
          <Button variant="ghost" size="sm" title="Düğümü sil" onClick={() => removeNode(node.id)}>
            <Trash2 size={14} />
          </Button>
        )}
      </div>

      <IssueList issues={issues} />

      {data.kind !== 'start' && (
        <Field label="Kart adı">
          <Input value={data.label ?? ''} placeholder={meta.title} onChange={(e) => update({ label: e.target.value })} />
        </Field>
      )}

      {data.kind === 'say' && (
        <Field label="Söylenecek metin" hint={VAR_HINT}>
          <Textarea rows={4} value={data.text ?? ''} onChange={(e) => update({ text: e.target.value })} />
        </Field>
      )}

      {data.kind === 'kb_answer' && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">Bilgi tabanları</div>
          <KBPicker value={data.kb_ids ?? []} onChange={(kb_ids) => update({ kb_ids })} />
        </div>
      )}

      {(data.kind === 'llm_task' || data.kind === 'llm_router' || data.kind === 'collect' || data.kind === 'kb_answer') && (
        <Field
          label={data.kind === 'llm_task' ? 'Görev talimatı' : 'Ek talimat (isteğe bağlı)'}
          hint={
            data.kind === 'llm_router'
              ? 'Seçeneklere yönlendirme talimatı otomatik eklenir.'
              : data.kind === 'kb_answer'
                ? 'Arama ve "yalnızca bulunan bilgiye dayan, uydurma" kuralları otomatik eklenir.'
              : data.kind === 'collect'
                ? 'Toplanacak alanlar talimata otomatik eklenir.'
                : VAR_HINT
          }
        >
          <Textarea rows={4} value={data.prompt ?? ''} onChange={(e) => update({ prompt: e.target.value })} />
        </Field>
      )}

      {data.kind === 'llm_task' && (
        <ExitsEditor
          title="Çıkışlar"
          hint="LLM, açıklamaya uyan durumda bu çıkışı seçer."
          items={data.exits ?? []}
          prefix="x"
          onChange={(exits) => update({ exits })}
        />
      )}
      {data.kind === 'kb_answer' && (
        <>
          <Field label="Getirilecek parça sayısı" hint="Her aramada LLM'e verilen en benzer doküman parçası sayısı.">
            <Input type="number" min={1} max={10} value={data.top_k ?? 4} onChange={(e) => update({ top_k: Number(e.target.value) || 4 })} />
          </Field>
          <ExitsEditor
            title="Çıkışlar"
            hint="Sorular bitince hangi dala geçileceği."
            items={data.exits ?? []}
            prefix="x"
            onChange={(exits) => update({ exits })}
          />
        </>
      )}
      {data.kind === 'llm_router' && (
        <ExitsEditor
          title="Seçenekler"
          hint="Her seçenek bir niyet; açıklama LLM'e ne zaman seçileceğini anlatır."
          items={data.routes ?? []}
          prefix="r"
          onChange={(routes) => update({ routes })}
        />
      )}
      {data.kind === 'collect' && (
        <>
          <FieldsEditor fields={data.fields ?? []} onChange={(fields) => update({ fields })} />
          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input type="checkbox" className="mt-1" checked={!!data.fallback} onChange={(e) => update({ fallback: e.target.checked })} />
            <span>
              "Bilgi verilemedi" çıkışı ekle
              <span className="block text-xs text-slate-400">Arayan bilgiyi bilmiyor veya vermek istemiyorsa ajan ısrar etmez, bu çıkıştan devam eder.</span>
            </span>
          </label>
        </>
      )}
      {data.kind === 'condition' && <RulesEditor rules={data.rules ?? []} onChange={(rules) => update({ rules })} />}

      {data.kind === 'http_request' && <HttpEditor data={data} update={update} />}

      {data.kind === 'transfer' && (
        <>
          <Field label="Aktarılacak birim" hint="Ör. Fatura birimi. Temsilciye giden notta görünür.">
            <Input value={data.target ?? ''} placeholder="Müşteri hizmetleri" onChange={(e) => update({ target: e.target.value })} />
          </Field>
          <Field label="Aktarma metni" hint={`Aktarmadan önce arayana okunur. ${VAR_HINT}`}>
            <Textarea rows={3} value={data.text ?? ''} onChange={(e) => update({ text: e.target.value || null })} />
          </Field>
          <label className="flex items-start gap-2 text-sm text-slate-600">
            <input type="checkbox" className="mt-1" checked={data.summary ?? true} onChange={(e) => update({ summary: e.target.checked })} />
            <span>
              Temsilci için özet hazırla
              <span className="block text-xs text-slate-400">Görüşme, arayana bir şey tekrar sorulmadan devam edilebilsin diye birkaç cümleyle özetlenir.</span>
            </span>
          </label>
          <p className="text-xs text-slate-400">Çağrı sonucu her zaman <span className="font-mono">transferred</span> olur.</p>
        </>
      )}

      {data.kind === 'end' && (
        <>
          <Field label="Kapanış metni" hint="Boş bırakılırsa LLM görüşmeyi kendisi toparlayıp vedalaşır.">
            <Textarea rows={3} value={data.text ?? ''} onChange={(e) => update({ text: e.target.value || null })} />
          </Field>
          <Field label="Çağrı sonucu" hint="Test raporlarında bu etiket görünür.">
            <Input list="outcomes" value={data.outcome ?? ''} onChange={(e) => update({ outcome: e.target.value })} />
            <datalist id="outcomes">
              {OUTCOMES.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          </Field>
        </>
      )}

      <p className="font-mono text-[11px] text-slate-300">id: {node.id}</p>
    </fieldset>
  )
}

export function IssueList({ issues, onSelect }: { issues: Issue[]; onSelect?: (nodeId: string) => void }) {
  if (!issues.length) return null
  return (
    <ul className="space-y-1">
      {issues.map((issue, i) => (
        <li
          key={i}
          onClick={() => issue.node_id && onSelect?.(issue.node_id)}
          className={clsx(
            'flex gap-2 rounded-md px-2 py-1.5 text-xs',
            issue.severity === 'error' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-800',
            onSelect && issue.node_id && 'cursor-pointer hover:brightness-95',
          )}
        >
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          {issue.message}
        </li>
      ))}
    </ul>
  )
}

function ListHeader({ title, hint, onAdd }: { title: string; hint?: string; onAdd: () => void }) {
  return (
    <div className="flex items-end justify-between">
      <div>
        <div className="text-xs font-medium text-slate-600">{title}</div>
        {hint && <div className="text-xs text-slate-400">{hint}</div>}
      </div>
      <Button size="sm" variant="ghost" onClick={onAdd}>
        <Plus size={13} /> Ekle
      </Button>
    </div>
  )
}

function RemoveButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="shrink-0 text-slate-300 hover:text-rose-500" onClick={onClick} title="Kaldır">
      <X size={14} />
    </button>
  )
}

function ExitsEditor(props: { title: string; hint: string; items: Exit[]; prefix: string; onChange: (items: Exit[]) => void }) {
  const { items, onChange } = props
  return (
    <div className="space-y-2">
      <ListHeader title={props.title} hint={props.hint} onAdd={() => onChange([...items, { id: uid(props.prefix), description: '' }])} />
      {items.map((item, i) => (
        <div key={item.id} className="flex items-center gap-2">
          <Input
            value={item.description}
            placeholder="Ör. Fatura veya ödeme sorusu"
            onChange={(e) => onChange(items.map((it, j) => (j === i ? { ...it, description: e.target.value } : it)))}
          />
          <RemoveButton onClick={() => onChange(items.filter((_, j) => j !== i))} />
        </div>
      ))}
    </div>
  )
}

function FieldsEditor({ fields, onChange }: { fields: CollectField[]; onChange: (fields: CollectField[]) => void }) {
  const set = (i: number, patch: Partial<CollectField>) => onChange(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)))
  return (
    <div className="space-y-2">
      <ListHeader
        title="Toplanacak bilgiler"
        hint="Alan adı değişken adı olur (küçük harf, rakam, _)."
        onAdd={() => onChange([...fields, { name: '', description: '', type: 'string', required: true }])}
      />
      {fields.map((f, i) => (
        <div key={i} className="space-y-1.5 rounded-lg border border-slate-200 p-2">
          <div className="flex items-center gap-2">
            <Input
              className="font-mono"
              value={f.name}
              placeholder="musteri_no"
              onChange={(e) => set(i, { name: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
            />
            <Select className="w-28" value={f.type} onChange={(e) => set(i, { type: e.target.value as CollectField['type'] })}>
              <option value="string">Metin</option>
              <option value="number">Sayı</option>
              <option value="boolean">Evet/Hayır</option>
            </Select>
            <RemoveButton onClick={() => onChange(fields.filter((_, j) => j !== i))} />
          </div>
          <Input value={f.description} placeholder="Açıklama (LLM'e ne alınacağını anlatır)" onChange={(e) => set(i, { description: e.target.value })} />
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            <input type="checkbox" checked={f.required} onChange={(e) => set(i, { required: e.target.checked })} />
            Zorunlu
          </label>
        </div>
      ))}
    </div>
  )
}

function HttpEditor({ data, update }: { data: NodeContent; update: (patch: Partial<NodeContent>) => void }) {
  const method = data.method ?? 'GET'
  const headers = data.headers ?? []
  const outputs = data.outputs ?? []
  const setHeader = (i: number, patch: Partial<Header>) => update({ headers: headers.map((h, j) => (j === i ? { ...h, ...patch } : h)) })
  const setOutput = (i: number, patch: Partial<HttpOutput>) => update({ outputs: outputs.map((o, j) => (j === i ? { ...o, ...patch } : o)) })
  return (
    <>
      <Field label="İstek" hint={`Adreste değişken kullanılabilir, değerler adrese uygun şekilde kodlanır. ${VAR_HINT}`}>
        <div className="flex gap-2">
          <div className="w-24 shrink-0">
            <Select value={method} onChange={(e) => update({ method: e.target.value as HttpMethod })}>
              {HTTP_METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </div>
          <Input className="font-mono" value={data.url ?? ''} placeholder="https://api.ornek.com/siparis/{{ siparis_no }}" onChange={(e) => update({ url: e.target.value })} />
        </div>
      </Field>

      <div className="space-y-2">
        <ListHeader
          title="Başlıklar"
          hint="API anahtarını buraya açık yazmayın: sunucuda SECRET_CRM_TOKEN gibi tanımlayıp {{ secret.crm_token }} ile kullanın. Gizli değerler akışta saklanmaz, kayıtlarda maskelenir."
          onAdd={() => update({ headers: [...headers, { name: '', value: '' }] })}
        />
        {headers.map((h, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input className="font-mono" value={h.name} placeholder="Ad" onChange={(e) => setHeader(i, { name: e.target.value })} />
            <Input className="font-mono" value={h.value} placeholder="Değer" onChange={(e) => setHeader(i, { value: e.target.value })} />
            <RemoveButton onClick={() => update({ headers: headers.filter((_, j) => j !== i) })} />
          </div>
        ))}
      </div>

      {method !== 'GET' && (
        <Field label="Gövde (JSON)" hint='Değişkenleri tırnak içinde kullanın: {"no": "{{ musteri_no }}"}. Değerler JSON için kaçışlanır.'>
          <Textarea className="font-mono text-xs" rows={4} value={data.body ?? ''} onChange={(e) => update({ body: e.target.value })} />
        </Field>
      )}

      <div className="space-y-2">
        <ListHeader
          title="Cevaptan alınacak değerler"
          hint="Cevaptaki alanın yolu (ör. durum veya veri.saatler.0) ve yazılacağı değişken."
          onAdd={() => update({ outputs: [...outputs, { variable: '', path: '' }] })}
        />
        {outputs.map((o, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input className="font-mono" value={o.path} placeholder="yol" onChange={(e) => setOutput(i, { path: e.target.value })} />
            <span className="text-slate-300">→</span>
            <Input
              className="font-mono"
              value={o.variable}
              placeholder="degisken"
              onChange={(e) => setOutput(i, { variable: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
            />
            <RemoveButton onClick={() => update({ outputs: outputs.filter((_, j) => j !== i) })} />
          </div>
        ))}
      </div>

      <Field label="Zaman aşımı (sn)" hint="Cevap gelmezse veya 2xx dışında bir durum dönerse 'Hata' çıkışına gidilir.">
        <Input type="number" min={1} max={30} value={data.timeout ?? 10} onChange={(e) => update({ timeout: Math.min(30, Math.max(1, Number(e.target.value) || 10)) })} />
      </Field>
    </>
  )
}

function RulesEditor({ rules, onChange }: { rules: Rule[]; onChange: (rules: Rule[]) => void }) {
  const variables = useEditor(useShallow((s) => knownVariables(s.nodes, s.variables)))
  const set = (i: number, patch: Partial<Rule>) => onChange(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  return (
    <div className="space-y-2">
      <ListHeader
        title="Kurallar"
        hint="Yukarıdan aşağı ilk sağlanan kural seçilir; hiçbiri sağlanmazsa 'Diğer durumlar'."
        onAdd={() => onChange([...rules, { id: uid('k'), variable: '', operator: 'eq', value: '' }])}
      />
      <datalist id="known-variables">
        {variables.map((v) => (
          <option key={v} value={v} />
        ))}
      </datalist>
      {rules.map((r, i) => {
        const needsValue = OPERATORS.find((o) => o.value === r.operator)?.needsValue
        return (
          <div key={r.id} className="space-y-1.5 rounded-lg border border-slate-200 p-2">
            <div className="flex items-center gap-2">
              <Input className="font-mono" list="known-variables" value={r.variable} placeholder="degisken" onChange={(e) => set(i, { variable: e.target.value })} />
              <RemoveButton onClick={() => onChange(rules.filter((_, j) => j !== i))} />
            </div>
            <div className="flex gap-2">
              <Select value={r.operator} onChange={(e) => set(i, { operator: e.target.value as Rule['operator'] })}>
                {OPERATORS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
              {needsValue && <Input value={r.value} placeholder="değer" onChange={(e) => set(i, { value: e.target.value })} />}
            </div>
          </div>
        )
      })}
    </div>
  )
}
