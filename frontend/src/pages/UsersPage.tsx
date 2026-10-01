import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Button, ErrorText, Field, Input, Modal, Select } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { Role, User } from '../lib/types'

const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: 'admin', label: 'Yönetici', hint: 'Kullanıcıları ve tüm ajanları yönetir' },
  { value: 'editor', label: 'Editör', hint: 'Akış oluşturur, düzenler, yayınlar ve test eder' },
  { value: 'viewer', label: 'İzleyici', hint: 'Akışları görüntüler ve test eder' },
]

export default function UsersPage() {
  const me = useAuth((s) => s.user)
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const users = useQuery({ queryKey: ['users'], queryFn: () => api<User[]>('/api/users') })

  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<User> }) =>
      api<User>(`/api/users/${id}`, { method: 'PATCH', body: patch }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Kullanıcılar</h1>
        <Button variant="primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> Kullanıcı ekle
        </Button>
      </div>
      <ErrorText error={users.error ?? update.error} />
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Kullanıcı</th>
              <th className="px-4 py-2 font-medium">Rol</th>
              <th className="px-4 py-2 font-medium">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.data?.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2">
                  <div className="font-medium">{u.name || '—'}</div>
                  <div className="text-xs text-slate-500">{u.email}</div>
                </td>
                <td className="px-4 py-2">
                  <Select
                    className="w-36"
                    value={u.role}
                    disabled={u.id === me?.id}
                    onChange={(e) => update.mutate({ id: u.id, patch: { role: e.target.value as Role } })}
                  >
                    {ROLES.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </Select>
                </td>
                <td className="px-4 py-2">
                  <label className="flex items-center gap-2 text-slate-600">
                    <input
                      type="checkbox"
                      checked={u.is_active}
                      disabled={u.id === me?.id}
                      onChange={(e) => update.mutate({ id: u.id, patch: { is_active: e.target.checked } })}
                    />
                    {u.is_active ? 'Aktif' : 'Pasif'}
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating && <CreateUserDialog onClose={() => setCreating(false)} />}
    </div>
  )
}

function CreateUserDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ email: '', name: '', password: '', role: 'editor' as Role })
  const create = useMutation({
    mutationFn: () => api<User>('/api/users', { method: 'POST', body: form }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value })

  return (
    <Modal
      title="Kullanıcı ekle"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Vazgeç</Button>
          <Button variant="primary" disabled={create.isPending} onClick={() => create.mutate()}>
            Ekle
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="E-posta">
          <Input type="email" value={form.email} onChange={set('email')} autoFocus />
        </Field>
        <Field label="Ad soyad">
          <Input value={form.name} onChange={set('name')} />
        </Field>
        <Field label="Geçici şifre" hint="En az 6 karakter.">
          <Input type="password" value={form.password} onChange={set('password')} />
        </Field>
        <Field label="Rol" hint={ROLES.find((r) => r.value === form.role)?.hint}>
          <Select value={form.role} onChange={set('role')}>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorText error={create.error} />
      </div>
    </Modal>
  )
}
