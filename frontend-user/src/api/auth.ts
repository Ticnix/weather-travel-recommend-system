import http from './http'

export interface AuthUser {
  id: number
  username: string
  nickname?: string | null
  email?: string | null
  role: string
  avatar?: string | null
  is_active: boolean
  /** 体质偏好：normal / cold（怕冷）/ heat（怕热），用于生活指数个性化排序 */
  body_preference?: string
  created_at: string
  updated_at: string
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: AuthUser
}

const TOKEN_KEY = 'wt_token'
const USER_KEY = 'wt_user'

// ===== token / user 本地存储 =====
export function saveAuth(res: LoginResult) {
  localStorage.setItem(TOKEN_KEY, res.access_token)
  localStorage.setItem(USER_KEY, JSON.stringify(res.user))
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isLoggedIn(): boolean {
  return !!getToken()
}

// ===== 接口 =====
export async function login(username: string, password: string): Promise<LoginResult> {
  return http.post('/users/login', { username, password })
}

export async function register(payload: {
  username: string
  password: string
  nickname?: string
  email?: string
}): Promise<AuthUser> {
  return http.post('/users/register', payload)
}

export async function fetchMe(): Promise<AuthUser> {
  return http.get('/users/me')
}

/**
 * 更新当前用户资料（昵称 / 邮箱等）。
 *
 * 只允许改自己的资料：user_id 从本地登录态取，避免调用方传错 id 改到别人。
 * 成功后同步本地缓存，刷新后首屏即为新值。
 */
export async function updateProfile(payload: {
  nickname?: string
  email?: string | null
}): Promise<AuthUser> {
  const user = getStoredUser()
  if (!user) throw new Error('未登录')
  const updated = (await http.put(`/users/${user.id}`, payload)) as unknown as AuthUser
  localStorage.setItem(USER_KEY, JSON.stringify({ ...user, ...updated }))
  return updated
}
