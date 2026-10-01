import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { AudioLines, LogOut } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { hasRole, useAuth } from '../lib/auth'

const ROLE_LABEL = { admin: 'Yönetici', editor: 'Editör', viewer: 'İzleyici' } as const

export default function Layout() {
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()

  const link = ({ isActive }: { isActive: boolean }) =>
    clsx('rounded-md px-3 py-1.5 text-sm', isActive ? 'bg-slate-100 font-medium text-slate-900' : 'text-slate-600 hover:text-slate-900')

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-4 border-b border-slate-200 bg-white px-4">
        <NavLink to="/" className="flex items-center gap-2 font-semibold text-slate-900">
          <AudioLines size={18} className="text-indigo-600" />
          DialogAI
        </NavLink>
        <nav className="flex gap-1">
          <NavLink to="/" end className={link}>
            Ajanlar
          </NavLink>
          <NavLink to="/knowledge" className={link}>
            Bilgi Tabanları
          </NavLink>
          {hasRole(user, 'admin') && (
            <NavLink to="/users" className={link}>
              Kullanıcılar
            </NavLink>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-slate-600">
            {user?.name || user?.email}
            {user && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">{ROLE_LABEL[user.role]}</span>}
          </span>
          <button
            className="text-slate-400 hover:text-slate-700"
            title="Çıkış yap"
            onClick={() => {
              logout()
              queryClient.clear()
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  )
}
