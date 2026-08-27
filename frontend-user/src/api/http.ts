import axios from 'axios'

// 统一 axios 实例：/api 由 vite 代理到后端 8000
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
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
