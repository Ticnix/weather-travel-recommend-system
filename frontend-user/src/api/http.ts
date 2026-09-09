import axios from 'axios'

// 统一 axios 实例：/api 由 vite 代理到后端 8000
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截：自动携带 JWT（内联读取，避免与 auth.ts 循环依赖）
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('wt_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：解包统一响应体 { code, message, data }
http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => Promise.reject(err),
)

export default http
