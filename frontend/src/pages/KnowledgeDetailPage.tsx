import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, FileText, Loader2, MessageSquareText, Plus, Search, Trash2, Upload, Users } from 'lucide-react'
import { useMemo, useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { TagChip } from '../components/TagInput'
import { Button, ErrorText, Input } from '../components/ui'
import DocumentDialog from '../knowledge/DocumentDialog'
import EntryDialog from '../knowledge/EntryDialog'
import SearchTester from '../knowledge/SearchTester'
import { TAG_RULE } from '../knowledge/tags'
import { api, ApiError } from '../lib/api'
import { hasRole, useAuth } from '../lib/auth'
import { formatBytes } from '../lib/knowledge'
import type { DocumentStatus, KBDocument, KnowledgeBaseDetail } from '../lib/types'

const ACCEPT = '.pdf,.docx,.txt,.md'
const STATUS: Record<DocumentStatus, { label: string; tone: string }> = {
  pending: { label: 'Sırada', tone: 'bg-slate-100 text-slate-600' },
  processing: { label: 'İşleniyor', tone: 'bg-sky-50 text-sky-700' },
  ready: { label: 'Hazır', tone: 'bg-emerald-50 text-emerald-700' },
  failed: { label: 'Hata', tone: 'bg-rose-50 text-rose-700' },
}
const UNTAGGED = '__etiketsiz__'
type KindFilter = 'all' | 'qa' | 'file'
const dateFmt = new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' })

export default function KnowledgeDetailPage() {
  const { kbId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const token = useAuth((s) => s.token)
  const canEdit = hasRole(useAuth((s) => s.user), 'editor')
  const fileInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [text, setText] = useState('')
  const [kind, setKind] = useState<KindFilter>('all')
  const [tagFilter, setTagFilter] = useState<string[]>([])
  // null: closed; "new": adding a question-answer; otherwise the entry being viewed.
  const [open, setOpen] = useState<KBDocument | 'new' | null>(null)
  const [confirmingKbDelete, setConfirmingKbDelete] = useState(false)

  const kb = useQuery({
    queryKey: ['knowledge-base', kbId],
    queryFn: () => api<KnowledgeBaseDetail>(`/api/knowledge-bases/${kbId}`),
    // Poll while files are being indexed.
    refetchInterval: (q) =>
      q.state.data?.documents.some((d) => d.status === 'pending' || d.status === 'processing') ? 1000 : false,
  })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['knowledge-base', kbId] })
    queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
    queryClient.invalidateQueries({ queryKey: ['tags'] })
  }

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      // multipart: the api() helper sends JSON, so post the form directly.
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      const res = await fetch(`/api/knowledge-bases/${kbId}/documents`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })
      if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Yükleme başarısız')
    },
    onSuccess: refresh,
  })
  const removeEntry = useMutation({
    mutationFn: (docId: string) => api(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
  const removeKb = useMutation({
    mutationFn: () => api(`/api/knowledge-bases/${kbId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      navigate('/knowledge')
    },
  })

  const entries = useMemo(() => kb.data?.documents ?? [], [kb.data])
  const kbTags = useMemo(() => [...new Set(entries.flatMap((e) => e.tags))].sort((a, b) => a.localeCompare(b, 'tr')), [entries])
  const visible = useMemo(() => {
    const needle = text.trim().toLocaleLowerCase('tr-TR')
    return entries.filter((e) => {
      if (kind !== 'all' && e.kind !== kind) return false
      if (tagFilter.length) {
        const matches = tagFilter.some((t) => (t === UNTAGGED ? e.tags.length === 0 : e.tags.includes(t)))
        if (!matches) return false
      }
      if (!needle) return true
      return [e.filename, e.question, e.answer, ...e.tags].some((s) => s?.toLocaleLowerCase('tr-TR').includes(needle))
    })
  }, [entries, text, kind, tagFilter])
  const counts = { qa: entries.filter((e) => e.kind === 'qa').length, file: entries.filter((e) => e.kind === 'file').length }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    if (canEdit && e.dataTransfer.files.length) upload.mutate([...e.dataTransfer.files])
  }
  const toggleTag = (t: string) => setTagFilter((f) => (f.includes(t) ? f.filter((x) => x !== t) : [...f, t]))

  if (kb.error) return <div className="p-6"><ErrorText error={kb.error} /></div>
  if (!kb.data) return <div className="flex h-full items-center justify-center text-slate-400"><Loader2 className="animate-spin" /></div>

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="flex items-start gap-3">
        <Link to="/knowledge" className="mt-1 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
          <ArrowLeft size={16} />
        </Link>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{kb.data.name}</h1>
          <p className="text-sm text-slate-500">
            {kb.data.description || 'Açıklama yok'} · {counts.qa} soru-cevap · {counts.file} doküman · {kb.data.chunk_count} parça
          </p>
        </div>
        {canEdit &&
          (confirmingKbDelete ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-500">Tüm girdiler silinecek; bu bilgi tabanını kullanan akışlar hata verir.</span>
              <Button onClick={() => setConfirmingKbDelete(false)}>Vazgeç</Button>
              <Button variant="danger" onClick={() => removeKb.mutate()}>
                Sil
              </Button>
            </div>
          ) : (
            <Button variant="ghost" className="text-rose-600" onClick={() => setConfirmingKbDelete(true)}>
              <Trash2 size={14} /> Bilgi tabanını sil
            </Button>
          ))}
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div
          className="relative space-y-3"
          onDragOver={(e) => {
            if (!canEdit) return
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={(e) => e.currentTarget.contains(e.relatedTarget as Node) || setDragging(false)}
          onDrop={onDrop}
        >
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-48 flex-1">
              <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
              <Input className="pl-8" value={text} onChange={(e) => setText(e.target.value)} placeholder="Girdilerde ara…" />
            </div>
            <div className="flex rounded-md bg-slate-100 p-0.5 text-xs">
              {(
                [
                  ['all', `Tümü (${entries.length})`],
                  ['qa', `Soru-cevap (${counts.qa})`],
                  ['file', `Doküman (${counts.file})`],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setKind(value)}
                  className={clsx('rounded px-2.5 py-1', kind === value ? 'bg-white font-medium shadow-sm' : 'text-slate-500')}
                >
                  {label}
                </button>
              ))}
            </div>
            {canEdit && (
              <>
                <Button onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
                  <Upload size={14} /> {upload.isPending ? 'Yükleniyor…' : 'Dosya yükle'}
                </Button>
                <Button variant="primary" onClick={() => setOpen('new')}>
                  <Plus size={14} /> Soru-cevap ekle
                </Button>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files?.length) upload.mutate([...e.target.files])
                    e.target.value = ''
                  }}
                />
              </>
            )}
          </div>

          {(kbTags.length > 0 || tagFilter.length > 0 || entries.length > 0) && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-slate-400">Etiket:</span>
              {kbTags.map((t) => (
                <TagChip key={t} tag={t} active={tagFilter.includes(t)} onClick={() => toggleTag(t)} />
              ))}
              <button
                onClick={() => toggleTag(UNTAGGED)}
                className={clsx(
                  'rounded-full px-2 py-0.5',
                  tagFilter.includes(UNTAGGED) ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                )}
              >
                Etiketsiz (herkese)
              </button>
              {tagFilter.length > 0 && (
                <button className="text-slate-400 hover:text-slate-700" onClick={() => setTagFilter([])}>
                  temizle
                </button>
              )}
              <Link to="/knowledge/tags" className="ml-auto text-indigo-600 hover:underline">
                Etiketleri yönet
              </Link>
            </div>
          )}

          <ErrorText error={upload.error ?? removeEntry.error} />

          {entries.length === 0 ? (
            <EmptyState canEdit={canEdit} onAdd={() => setOpen('new')} onUpload={() => fileInput.current?.click()} />
          ) : visible.length === 0 ? (
            <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">Filtreye uyan girdi yok.</p>
          ) : (
            <ul className="space-y-2">
              {visible.map((e) => (
                <EntryRow key={e.id} entry={e} canEdit={canEdit} onOpen={() => setOpen(e)} onDelete={() => removeEntry.mutate(e.id)} />
              ))}
            </ul>
          )}

          {dragging && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-xl border-2 border-dashed border-emerald-400 bg-emerald-50/90 text-sm font-medium text-emerald-800">
              <Upload size={18} className="mr-2" /> Dosyaları bırakın · PDF, DOCX, TXT, MD · en fazla 25 MB
            </div>
          )}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-4">
          <SearchTester kbId={kbId} />
          <section className="rounded-xl border border-violet-100 bg-violet-50/40 p-4 text-xs text-slate-600">
            <div className="mb-1 flex items-center gap-1.5 font-medium text-violet-800">
              <Users size={13} /> Etiketler nasıl çalışır?
            </div>
            <p>{TAG_RULE}</p>
            <p className="mt-1.5">
              Etiketleri{' '}
              <Link to="/knowledge/tags" className="font-medium text-violet-800 hover:underline">
                Etiketler
              </Link>{' '}
              ekranında oluşturabilir, girdiyi eklerken de yenisini tanımlayabilirsiniz.
            </p>
            <p className="mt-1.5">
              Arayanın etiketleri akışın <b>Genel ayarlar → Arayan etiketleri</b> alanından gelir; ör. çağrı başında arayan numarasını sorgulayan
              bir HTTP Aracı'nın yazdığı <span className="font-mono">{'{{ musteri_tipi }}'}</span>.
            </p>
          </section>
        </aside>
      </div>

      {open === 'new' && <EntryDialog kbId={kbId} entry={null} canEdit={canEdit} onClose={() => setOpen(null)} onSaved={refresh} />}
      {open && open !== 'new' && open.kind === 'qa' && (
        <EntryDialog kbId={kbId} entry={open} canEdit={canEdit} onClose={() => setOpen(null)} onSaved={refresh} />
      )}
      {open && open !== 'new' && open.kind === 'file' && (
        <DocumentDialog kbId={kbId} doc={open} canEdit={canEdit} onClose={() => setOpen(null)} onChanged={refresh} />
      )}
    </div>
  )
}

function EntryRow({ entry: e, canEdit, onOpen, onDelete }: { entry: KBDocument; canEdit: boolean; onOpen: () => void; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const busy = e.status === 'pending' || e.status === 'processing'
  return (
    <li className="group flex gap-3 rounded-xl border border-slate-200 bg-white p-3 hover:border-slate-300">
      <span className={clsx('mt-0.5 h-fit rounded-md p-1.5', e.kind === 'qa' ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500')}>
        {e.kind === 'qa' ? <MessageSquareText size={15} /> : <FileText size={15} />}
      </span>
      <button className="min-w-0 flex-1 text-left" onClick={onOpen} disabled={busy}>
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{e.kind === 'qa' ? e.question : e.filename}</span>
          {e.kind === 'file' && e.status !== 'ready' && (
            <span className={clsx('inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs', STATUS[e.status].tone)}>
              {e.status === 'processing' && <Loader2 size={10} className="animate-spin" />}
              {STATUS[e.status].label}
            </span>
          )}
        </div>
        {e.kind === 'qa' ? (
          <p className="line-clamp-2 text-sm text-slate-500">{e.answer}</p>
        ) : (
          <p className="text-xs text-slate-500">
            {formatBytes(e.size)}
            {e.status === 'ready' && ` · ${e.chunk_count} parça`}
            {e.edited_chunks > 0 && <span className="text-amber-700"> · {e.edited_chunks} parça elle düzenlendi</span>}
          </p>
        )}
        {e.error && <p className="text-xs text-rose-600">{e.error}</p>}
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {e.tags.length ? e.tags.map((t) => <TagChip key={t} tag={t} />) : <span className="text-xs text-slate-400">Herkese</span>}
          <span className="ml-auto text-[11px] text-slate-300">{dateFmt.format(new Date(e.updated_at ?? e.created_at))}</span>
        </div>
      </button>
      {canEdit && (
        <div className="flex shrink-0 items-start">
          {confirming ? (
            <span className="flex gap-1">
              <Button size="sm" onClick={() => setConfirming(false)}>
                Vazgeç
              </Button>
              <Button size="sm" variant="danger" onClick={onDelete}>
                Sil
              </Button>
            </span>
          ) : (
            <button
              title="Sil"
              className="rounded p-1 text-slate-300 opacity-0 transition-opacity hover:bg-rose-50 hover:text-rose-600 group-hover:opacity-100"
              onClick={() => setConfirming(true)}
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      )}
    </li>
  )
}

function EmptyState({ canEdit, onAdd, onUpload }: { canEdit: boolean; onAdd: () => void; onUpload: () => void }) {
  return (
    <div className="grid gap-3 rounded-xl border border-dashed border-slate-300 p-6 sm:grid-cols-2">
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 font-medium">
          <MessageSquareText size={16} className="text-indigo-600" /> Soru-cevap
        </div>
        <p className="text-sm text-slate-500">Sık sorulan bir soruyu ve cevabını elle yazın. Kaydettiğiniz anda aranabilir.</p>
        {canEdit && (
          <Button size="sm" variant="primary" onClick={onAdd}>
            <Plus size={13} /> Soru-cevap ekle
          </Button>
        )}
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 font-medium">
          <FileText size={16} className="text-slate-500" /> Doküman
        </div>
        <p className="text-sm text-slate-500">PDF, Word veya metin dosyası yükleyin ya da buraya sürükleyin; parçalara ayrılır, parçalar düzenlenebilir.</p>
        {canEdit && (
          <Button size="sm" onClick={onUpload}>
            <Upload size={13} /> Dosya yükle
          </Button>
        )}
      </div>
    </div>
  )
}
