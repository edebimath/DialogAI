import { useAuth } from './auth'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Options = { method?: string; body?: unknown; form?: Record<string, string> }

export async function api<T>(path: string, { method = 'GET', body, form }: Options = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = useAuth.getState().token
  if (token) headers.Authorization = `Bearer ${token}`

  let payload: BodyInit | undefined
  if (form) {
    payload = new URLSearchParams(form)
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  const res = await fetch(path, { method, headers, body: payload })
  if (res.status === 401 && token) useAuth.getState().logout()
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return (res.status === 204 ? undefined : await res.json()) as T
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((d: { msg: string }) => d.msg).join(', ')
  } catch {
    // not JSON
  }
  return `İstek başarısız (${res.status})`
}

/** The token goes in the start message, not the URL, so it stays out of access logs. */
export function sessionSocketUrl(): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/api/sessions/ws`
}
