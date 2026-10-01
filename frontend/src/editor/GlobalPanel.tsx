import { Plus, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { TagChip } from '../components/TagInput'
import { Button, Field, Input, Textarea } from '../components/ui'
import { useTags } from '../lib/knowledge'
import { IssueList } from './Inspector'
import KBPicker from './KBPicker'
import { useEditor } from './store'

/** The values caller tags can take, so the flow's lookup can be made to produce them. */
function DefinedTags() {
  const tags = useTags()
  if (!tags.data?.length) return null
  return (
    <div className="-mt-3 flex flex-wrap items-center gap-1 text-xs text-slate-400">
      Tanımlı etiketler:
      {tags.data.map((t) => (
        <TagChip key={t.id} tag={t.name} />
      ))}
      <Link to="/knowledge/tags" className="text-indigo-600 hover:underline">
        yönet
      </Link>
    </div>
  )
}

/** Shown when no node is selected: persona, global rules, variables and all issues. */
export default function GlobalPanel() {
  const { global, variables, setGlobal, setVariables, issues, select, readOnly } = useEditor(
    useShallow((s) => ({
      global: s.global,
      variables: s.variables,
      setGlobal: s.setGlobal,
      setVariables: s.setVariables,
      issues: s.issues,
      select: s.select,
      readOnly: s.readOnly,
    })),
  )
  const setVar = (i: number, patch: Partial<(typeof variables)[number]>) =>
    setVariables(variables.map((v, j) => (j === i ? { ...v, ...patch } : v)))

  return (
    <fieldset disabled={readOnly} className="space-y-5">
      <div>
        <div className="font-medium">Genel ayarlar</div>
        <div className="text-xs text-slate-500">Tüm adımlarda geçerli. Bir karta tıklayarak onu düzenleyin.</div>
      </div>

      {issues.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">Akıştaki sorunlar</div>
          <IssueList issues={issues} onSelect={select} />
        </div>
      )}

      <Field label="Persona" hint="Ajanın kim olduğu ve nasıl konuştuğu.">
        <Textarea
          rows={4}
          value={global.persona}
          placeholder="Sen Örnek Telekom'un çağrı merkezi asistanısın..."
          onChange={(e) => setGlobal({ persona: e.target.value })}
        />
      </Field>
      <Field label="Genel kurallar" hint="Her adımda uyulacak kurallar.">
        <Textarea rows={3} value={global.rules} onChange={(e) => setGlobal({ rules: e.target.value })} />
      </Field>

      <div className="space-y-1">
        <div className="text-xs font-medium text-slate-600">Her adımda kullanılabilir bilgi tabanları</div>
        <div className="text-xs text-slate-400">Seçilirse ajan, şirketle ilgili sorularda her adımda arama yapabilir.</div>
        <KBPicker value={global.kb_ids ?? []} onChange={(kb_ids) => setGlobal({ kb_ids })} />
      </div>

      <Field
        label="Arayan etiketleri"
        hint={
          <>
            Bilgi tabanı aramalarında kullanılır; virgülle ayrılmış etiketler veya bir değişken (ör. bir HTTP Aracı'nın yazdığı{' '}
            <span className="font-mono">{'{{ musteri_tipi }}'}</span>). Doluysa etiketli girdiler yalnızca eşleşen arayanlara gösterilir; boşsa tüm girdiler
            herkese gösterilir.
          </>
        }
      >
        <Input
          className="font-mono"
          value={global.caller_tags ?? ''}
          placeholder="{{ musteri_tipi }}"
          onChange={(e) => setGlobal({ caller_tags: e.target.value })}
        />
      </Field>
      <DefinedTags />

      <div className="space-y-2">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xs font-medium text-slate-600">Değişkenler</div>
            <div className="text-xs text-slate-400">Çağrı başında bilinen değerler; testte değiştirilebilir.</div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => setVariables([...variables, { name: '', description: '', default: '' }])}>
            <Plus size={13} /> Ekle
          </Button>
        </div>
        {variables.map((v, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input
              className="font-mono"
              value={v.name}
              placeholder="ad"
              onChange={(e) => setVar(i, { name: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
            />
            <Input value={v.default ?? ''} placeholder="varsayılan" onChange={(e) => setVar(i, { default: e.target.value })} />
            <button type="button" className="text-slate-300 hover:text-rose-500" onClick={() => setVariables(variables.filter((_, j) => j !== i))}>
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </fieldset>
  )
}
