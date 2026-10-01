import clsx from 'clsx'
import { AlertCircle, ArrowRight, AudioLines, BookOpenText, Bot, Braces, CircleStop, GitBranch, Globe, Hand, Headset, Mic, PencilLine, PhoneOff, RotateCcw, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import { CATALOG } from '../editor/catalog'
import type { NodeKind, TraceEvent } from '../lib/types'

export interface NodeInfo {
  label: string
  kind: NodeKind
}

const END_REASON: Record<string, string> = {
  flow_ended: 'Akış bir Bitiş veya Aktarma kartıyla tamamlandı',
  caller_hangup: 'Simüle arayan telefonu kapattı',
  max_turns: 'Tur sınırına ulaşıldı',
  loop: 'Konuşma döngüye girdi',
  silence: 'Ajan cevap vermedi',
  user_hangup: 'Test eden kullanıcı çağrıyı bitirdi',
  client_disconnected: 'Bağlantı kesildi',
  timeout: 'Süre sınırı doldu',
  error: 'Hata nedeniyle sonlandı',
}

/** The call as it happened: conversation bubbles interleaved with what the system did. */
export default function Timeline({
  events,
  nodes,
  details,
  onNodeClick,
}: {
  events: TraceEvent[]
  nodes: Record<string, NodeInfo>
  details: boolean
  onNodeClick: (nodeId: string) => void
}) {
  let lastTtfb: number | null = null
  const rows: ReactNode[] = []

  for (const e of events) {
    const d = e.data as Record<string, any>
    switch (e.type) {
      case 'user_message':
        lastTtfb = null
        rows.push(
          <Bubble key={e.seq} side="user" ts={e.ts} tag={d.source === 'voice' ? 'sesli' : d.source === 'simulated' ? 'simüle arayan' : undefined}>
            {d.source === 'voice' && <Mic size={12} className="mr-1 inline -translate-y-px opacity-70" />}
            {d.source === 'simulated' && <Bot size={12} className="mr-1 inline -translate-y-px opacity-70" />}
            {d.text}
          </Bubble>,
        )
        break
      case 'voice_latency':
        rows.push(
          <Row
            key={e.seq}
            icon={<AudioLines size={12} />}
            ts={e.ts}
            tone={d.seconds > 2 ? 'warn' : undefined}
            text={`Arayan sustuktan sonra ajanın konuşmaya başlaması: ${d.seconds.toFixed(2)} sn`}
          />,
        )
        break
      case 'caller_hangup':
        rows.push(
          <Row
            key={e.seq}
            icon={<PhoneOff size={12} />}
            ts={e.ts}
            tone={d.success ? undefined : 'warn'}
            text={`Arayan telefonu kapattı (${d.success ? 'amacına ulaştı' : 'amacına ulaşamadı'}): ${d.reason}`}
          />,
        )
        break
      case 'empty_reply':
        rows.push(
          <Row
            key={e.seq}
            icon={<RotateCcw size={12} />}
            ts={e.ts}
            tone="warn"
            text={d.retried ? 'LLM boş cevap verdi, yeniden denendi' : 'LLM yine boş cevap verdi'}
          />,
        )
        break
      case 'interrupted':
        rows.push(<Row key={e.seq} icon={<Hand size={12} />} ts={e.ts} text="Arayan ajanın sözünü kesti" tone="warn" />)
        break
      case 'stt_time':
        if (details) rows.push(<Row key={e.seq} icon={<Timer size={12} />} ts={e.ts} text={`Konuşmayı yazıya çevirme: ${d.seconds.toFixed(2)} sn`} />)
        break
      case 'tts_ttfb':
        if (details) rows.push(<Row key={e.seq} icon={<Timer size={12} />} ts={e.ts} text={`Seslendirmenin başlaması: ${d.seconds.toFixed(2)} sn`} />)
        break
      case 'say':
        rows.push(
          <Bubble key={e.seq} side="bot" ts={e.ts} tag="Söylem">
            {d.text}
          </Bubble>,
        )
        break
      case 'bot_message':
        rows.push(
          <Bubble key={e.seq} side="bot" ts={e.ts} tag={lastTtfb !== null ? `${lastTtfb.toFixed(2)} sn` : undefined}>
            {d.text}
          </Bubble>,
        )
        lastTtfb = null
        break
      case 'llm_ttfb':
        lastTtfb = d.seconds
        if (details) rows.push(<Row key={e.seq} icon={<Timer size={12} />} ts={e.ts} text={`LLM ilk yanıt süresi: ${d.seconds.toFixed(2)} sn`} />)
        break
      case 'node_entered': {
        if (!details || d.node_type === 'start') break
        const info = e.node_id ? nodes[e.node_id] : undefined
        const kind = (info?.kind ?? d.node_type) as NodeKind
        rows.push(
          <button
            key={e.seq}
            onClick={() => e.node_id && onNodeClick(e.node_id)}
            className="flex w-full items-center gap-2 py-1 text-left text-xs text-slate-500 hover:text-indigo-600"
          >
            <ArrowRight size={12} />
            <span className={clsx('rounded px-1.5 py-0.5 font-medium', CATALOG[kind]?.tone)}>{info?.label || d.label || CATALOG[kind]?.title}</span>
            <span className="ml-auto font-mono text-[10px] text-slate-300">{e.ts.toFixed(1)}s</span>
          </button>,
        )
        break
      }
      case 'function_call':
        if (details)
          rows.push(
            <Row
              key={e.seq}
              icon={<Braces size={12} />}
              ts={e.ts}
              text={
                <>
                  <span className="font-mono">{d.name}</span>
                  {d.label && <span className="text-slate-600"> · {d.label}</span>}
                  {Object.keys(d.args ?? {}).length > 0 && <span className="font-mono text-slate-400"> {JSON.stringify(d.args)}</span>}
                </>
              }
            />,
          )
        break
      case 'variables_set':
        if (details)
          rows.push(
            <Row
              key={e.seq}
              icon={<PencilLine size={12} />}
              ts={e.ts}
              text={Object.entries(d.values ?? {})
                .map(([k, v]) => `${k} = ${JSON.stringify(v)}`)
                .join(', ')}
            />,
          )
        break
      case 'kb_search':
        rows.push(<KBSearchRow key={e.seq} ts={e.ts} data={d} details={details} />)
        break
      case 'http_request':
        rows.push(<HttpRow key={e.seq} ts={e.ts} data={d} details={details} />)
        break
      case 'transfer':
        rows.push(<TransferCard key={e.seq} ts={e.ts} data={d} />)
        break
      case 'condition_evaluated':
        if (details) rows.push(<Row key={e.seq} icon={<GitBranch size={12} />} ts={e.ts} text={`Koşul sonucu: ${d.matched === 'else' ? 'Diğer durumlar' : d.matched}`} />)
        break
      case 'error':
        rows.push(<Row key={e.seq} icon={<AlertCircle size={12} />} ts={e.ts} text={d.message} tone="error" />)
        break
      case 'session_ended':
        rows.push(
          <div key={e.seq} className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs">
            <div className="flex items-center gap-2 font-medium text-slate-700">
              <CircleStop size={13} /> Çağrı bitti · {e.ts.toFixed(1)} sn
            </div>
            <div className="mt-1 text-slate-500">
              Sonuç: <span className="font-mono text-slate-700">{d.outcome ?? '—'}</span> · {END_REASON[d.reason] ?? d.reason}
            </div>
          </div>,
        )
        break
    }
  }

  return <div className="space-y-1.5">{rows}</div>
}

interface KBHitView {
  document: string
  page: number | null
  score: number
  text: string
}

/** What the knowledge base returned for the agent's search; sources expand in detail mode. */
function KBSearchRow({ ts, data, details }: { ts: number; data: Record<string, any>; details: boolean }) {
  const hits = (data.hits ?? []) as KBHitView[]
  return (
    <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 px-2 py-1.5 text-xs">
      <div className="flex items-start gap-2 text-emerald-800">
        <BookOpenText size={12} className="mt-0.5 shrink-0" />
        <span className="min-w-0 flex-1">
          Bilgi tabanında arandı: <span className="italic">“{data.query}”</span> →{' '}
          {hits.length ? `${hits.length} kaynak` : 'bulunamadı'} ({data.ms} ms)
          {Array.isArray(data.tags) && (
            <span className="block text-violet-700">
              Arayan etiketleri: {data.tags.length ? data.tags.join(', ') : 'yok (yalnızca herkese açık girdiler)'}
            </span>
          )}
        </span>
        <span className="font-mono text-[10px] text-slate-300">{ts.toFixed(1)}s</span>
      </div>
      {details && hits.length > 0 && (
        <ul className="mt-1 space-y-1 pl-5">
          {hits.map((h, i) => (
            <li key={i} className="text-slate-600">
              <span className="font-medium">
                {h.document}
                {h.page ? `, s.${h.page}` : ''}
              </span>{' '}
              <span className="font-mono text-slate-400">{h.score.toFixed(2)}</span>
              <div className="line-clamp-2 text-slate-500">{h.text}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** An HTTP Aracı request: status and the values written; the raw reply in detail mode. */
function HttpRow({ ts, data, details }: { ts: number; data: Record<string, any>; details: boolean }) {
  const values = Object.entries((data.values ?? {}) as Record<string, unknown>)
  return (
    <div className={clsx('rounded-lg border px-2 py-1.5 text-xs', data.ok ? 'border-orange-100 bg-orange-50/50' : 'border-rose-100 bg-rose-50/60')}>
      <div className={clsx('flex items-start gap-2', data.ok ? 'text-orange-800' : 'text-rose-700')}>
        <Globe size={12} className="mt-0.5 shrink-0" />
        <span className="min-w-0 flex-1 break-all">
          <span className="font-mono font-medium">{data.method}</span> <span className="font-mono">{data.url}</span> →{' '}
          {data.status ?? '—'} ({data.ms} ms){!data.ok && data.error && <span className="block">{data.error}</span>}
        </span>
        <span className="font-mono text-[10px] text-slate-300">{ts.toFixed(1)}s</span>
      </div>
      {data.ok && values.length > 0 && (
        <div className="mt-1 pl-5 font-mono text-slate-600">
          {values.map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join(', ')}
        </div>
      )}
      {data.ok && (data.missing ?? []).length > 0 && (
        <div className="mt-1 pl-5 text-amber-700">Cevapta bulunamayan alanlar: {(data.missing as string[]).join(', ')}</div>
      )}
      {details && data.response && <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all pl-5 text-[11px] text-slate-500">{data.response}</pre>}
    </div>
  )
}

/** The handoff: where the call went and the note the human agent receives. */
function TransferCard({ ts, data }: { ts: number; data: Record<string, any> }) {
  const variables = Object.entries((data.variables ?? {}) as Record<string, unknown>)
  return (
    <div className="rounded-lg border border-fuchsia-200 bg-fuchsia-50/60 p-2.5 text-xs">
      <div className="flex items-center gap-2 font-medium text-fuchsia-800">
        <Headset size={13} /> Temsilciye aktarıldı{data.target ? `: ${data.target}` : ''}
        <span className="ml-auto font-mono text-[10px] font-normal text-slate-300">{ts.toFixed(1)}s</span>
      </div>
      {data.summary && <p className="mt-1.5 text-slate-700">{data.summary}</p>}
      {data.summary_error && <p className="mt-1.5 text-amber-700">{data.summary_error}</p>}
      {variables.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {variables.map(([k, v]) => (
            <span key={k} className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600 ring-1 ring-fuchsia-100">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Bubble({ side, ts, tag, children }: { side: 'user' | 'bot'; ts: number; tag?: string; children: ReactNode }) {
  return (
    <div className={clsx('flex flex-col', side === 'user' ? 'items-end' : 'items-start')}>
      <div
        className={clsx(
          'max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm',
          side === 'user' ? 'rounded-br-sm bg-indigo-600 text-white' : 'rounded-bl-sm bg-white text-slate-800 shadow-sm ring-1 ring-slate-200',
        )}
      >
        {children}
      </div>
      <div className="mt-0.5 px-1 text-[10px] text-slate-400">
        {side === 'user' ? 'Arayan' : 'Ajan'} · {ts.toFixed(1)}s{tag && ` · ${tag}`}
      </div>
    </div>
  )
}

function Row({ icon, ts, text, tone }: { icon: ReactNode; ts: number; text: ReactNode; tone?: 'error' | 'warn' }) {
  return (
    <div
      className={clsx(
        'flex items-start gap-2 py-0.5 text-xs',
        tone === 'error' ? 'text-rose-600' : tone === 'warn' ? 'text-amber-600' : 'text-slate-500',
      )}
    >
      <span className="mt-0.5">{icon}</span>
      <span className="min-w-0 flex-1 break-words">{text}</span>
      <span className="font-mono text-[10px] text-slate-300">{ts.toFixed(1)}s</span>
    </div>
  )
}
