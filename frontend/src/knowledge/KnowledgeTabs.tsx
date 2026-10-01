import clsx from 'clsx'
import { NavLink } from 'react-router-dom'

/** Switches between the knowledge bases and the tags they use. */
export default function KnowledgeTabs() {
  const tab = ({ isActive }: { isActive: boolean }) =>
    clsx('rounded-md px-3 py-1.5 text-sm', isActive ? 'bg-white font-medium text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800')
  return (
    <nav className="mb-5 inline-flex gap-1 rounded-lg bg-slate-100 p-1">
      <NavLink to="/knowledge" end className={tab}>
        Bilgi tabanları
      </NavLink>
      <NavLink to="/knowledge/tags" className={tab}>
        Etiketler
      </NavLink>
    </nav>
  )
}
