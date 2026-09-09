import http from './http'

export interface AuthUser {
  id: number
  username: string
  nickname?: string | null
  email?: string | null
  role: string
  avatar?: string | null
  is_active: boolean
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
