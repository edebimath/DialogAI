import clsx from 'clsx'
import { CheckCircle2, CircleSlash, Loader2, Scale, UserRound, XCircle } from 'lucide-react'
import type { ResultStatus, Verdict } from '../lib/types'

const STATUS: Record<ResultStatus, { label: string; tone: string }> = {
  pending: { label: 'Sırada', tone: 'bg-slate-100 text-slate-600' },
  running: { label: 'Çalışıyor', tone: 'bg-sky-50 text-sky-700' },
  passed: { label: 'Geçti', tone: 'bg-emerald-50 text-emerald-700' },
  failed: { label: 'Kaldı', tone: 'bg-rose-50 text-rose-700' },
  error: { label: 'Hata', tone: 'bg-amber-50 text-amber-800' },
  cancelled: { label: 'İptal', tone: 'bg-slate-100 text-slate-500' },
}

export function StatusBadge({ status }: { status: ResultStatus }) {
  const s = STATUS[status]
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium', s.tone)}>
      {status === 'running' && <Loader2 size={10} className="animate-spin" />}
      {s.label}
    </span>
  )
}

/** Why a simulated call passed or failed: rule checks, the judge's reasoning, the caller's view. */
export function VerdictCard({ verdict }: { verdict: Verdict | Record<string, never> }) {
  if (!('checks' in verdict)) return null
  return (
    <div className="space-y-2 text-sm">
      {verdict.error && <p className="rounded-md bg-amber-50 px-2 py-1.5 text-amber-800">{verdict.error}</p>}
      <ul className="space-y-1">
        {verdict.checks.map((c) => (
          <li key={c.name} className="flex items-start gap-2">
            {c.passed ? (
              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" />
            ) : (
              <XCircle size={15} className="mt-0.5 shrink-0 text-rose-600" />
            )}
            <span>
              {c.name}
              {c.detail && <span className="text-slate-500"> — {c.detail}</span>}
            </span>
          </li>
        ))}
        {verdict.judge && (
          <li className="flex items-start gap-2">
            {verdict.judge.passed ? (
              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" />
            ) : (
              <XCircle size={15} className="mt-0.5 shrink-0 text-rose-600" />
            )}
            <span>
              <span className="inline-flex items-center gap-1">
                <Scale size={12} /> Hakem
              </span>
              <span className="text-slate-500"> — {verdict.judge.reason}</span>
            </span>
          </li>
        )}
      </ul>
      {verdict.caller && (
        <p className="flex items-start gap-2 text-xs text-slate-500">
          {verdict.caller.success ? <UserRound size={13} className="mt-0.5" /> : <CircleSlash size={13} className="mt-0.5" />}
          Arayanın görüşü: {verdict.caller.success ? 'amacına ulaştı' : 'amacına ulaşamadı'} — {verdict.caller.reason}
        </p>
      )}
    </div>
  )
}
