import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Role, User } from './types'

interface AuthState {
  token: string | null
  user: User | null
  setSession: (token: string, user: User) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'dialogai-auth' },
  ),
)

const RANK: Record<Role, number> = { viewer: 0, editor: 1, admin: 2 }

export function hasRole(user: User | null, role: Role): boolean {
  return !!user && RANK[user.role] >= RANK[role]
}
