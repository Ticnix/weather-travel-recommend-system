import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'admin_token'
const USER_KEY = 'admin_user'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => {
    // 统一响应体 { code, message, data }
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      // 业务错误，且携带前端跳转的 auth 错误已在下方统一处理，这里拦截
      if (body.code === 401) {
        clearAdminAuth()
      }
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => {
    const status = err.response?.status
    if (status === 401) {
      clearAdminAuth()
      ElMessage.error('登录已过期，请重新登录')
    } else {
      ElMessage.error(err.response?.data?.message || err.response?.data?.detail || '网络错误，请重试')
    }
    return Promise.reject(err)
  },
)

export function setAdminAuth(token: string, user: unknown) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function getAdminToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getAdminUser<T = unknown>(): T | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function clearAdminAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export default http
