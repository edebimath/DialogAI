import clsx from 'clsx'
import type { NodeKind } from '../lib/types'
import { CATALOG, PALETTE_KINDS } from './catalog'

export const DRAG_MIME = 'application/dialogai-node'

export default function Palette({ onAdd }: { onAdd: (kind: NodeKind) => void }) {
  return (
    <aside className="w-56 shrink-0 overflow-y-auto border-r border-slate-200 bg-white p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Kartlar</h3>
      <div className="space-y-2">
        {PALETTE_KINDS.map((kind) => {
          const meta = CATALOG[kind]
          const Icon = meta.icon
          return (
            <button
              key={kind}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(DRAG_MIME, kind)
                e.dataTransfer.effectAllowed = 'move'
              }}
              onClick={() => onAdd(kind)}
              className="w-full cursor-grab rounded-lg border border-slate-200 p-2 text-left hover:border-indigo-300 hover:bg-indigo-50/40 active:cursor-grabbing"
              title="Canvas'a sürükleyin veya tıklayın"
            >
              <div className="flex items-center gap-2 text-sm font-medium">
                <span className={clsx('rounded-md p-1', meta.tone)}>
                  <Icon size={14} />
                </span>
                {meta.title}
              </div>
              <p className="mt-1 text-xs leading-snug text-slate-500">{meta.description}</p>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
