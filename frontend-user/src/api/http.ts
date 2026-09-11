import axios from 'axios'
import { message } from 'antd'

// 统一 axios 实例：/api 由 vite 代理到后端
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

const TOKEN_KEY = 'wt_token'

// 请求拦截：自动携带 JWT（内联读取，避免与 auth.ts 循环依赖）
http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：解包统一响应体 { code, message, data }，并做全局错误提示
http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      // 业务错误：统一弹出后端返回的提示
      const msg = body.message || '请求失败'
      message.error(msg)
      return Promise.reject(new Error(msg))
    }
    return body
  },
  (err) => {
    // 登录接口的失败信息由登录页自行展示，避免重复提示
    const url: string = err.config?.url ?? ''
    const isLoginApi = url.includes('/users/login')

    if (!isLoginApi) {
      const status = err.response?.status
      const detail = err.response?.data?.detail || err.response?.data?.message
      if (status === 401) {
        // 凭证失效：清除本地 token，跳转由路由/页面自行处理
        localStorage.removeItem(TOKEN_KEY)
        message.error('登录已过期，请重新登录')
      } else if (err.code === 'ECONNABORTED') {
        message.error('请求超时，请稍后重试')
      } else if (!err.response) {
        message.error('网络异常，请检查网络后重试')
      } else {
        message.error(detail || '服务异常，请稍后重试')
      }
    }
    return Promise.reject(err)
  },
)

export default http
