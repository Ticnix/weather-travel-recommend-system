import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosRequestConfig, AxiosResponse } from 'axios'

// antd 的 message 会真的往 DOM 里挂提示，这里换成 spy 便于断言
vi.mock('antd', () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

import { message } from 'antd'
import http from './http'

const TOKEN_KEY = 'wt_token'

/**
 * 用自定义 adapter 捕获真实经过拦截器后的请求配置。
 *
 * 这样做的好处：走的是**完整的拦截器链**（而不是直接调用
 * `interceptors.request.handlers[0]` 那种依赖 axios 内部结构的方式），
 * 以后 axios 内部实现变了，测试也不会莫名失效。
 */
function captureRequest(response: unknown = { code: 0, message: 'ok', data: { ok: true } }) {
  const captured: { config?: AxiosRequestConfig } = {}
  const adapter = async (config: AxiosRequestConfig): Promise<AxiosResponse> => {
    captured.config = config
    return {
      data: response,
      status: 200,
      statusText: 'OK',
      headers: {},
      config: config as never,
    }
  }
  return { captured, adapter }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

afterEach(() => {
  localStorage.clear()
})

describe('请求拦截器：自动携带 JWT', () => {
  it('已登录时带上 Authorization 头', async () => {
    localStorage.setItem(TOKEN_KEY, 'token-abc')
    const { captured, adapter } = captureRequest()

    await http.get('/weather/current', { adapter })

    expect(captured.config?.headers?.Authorization).toBe('Bearer token-abc')
  })

  it('未登录时不带 Authorization 头', async () => {
    const { captured, adapter } = captureRequest()

    await http.get('/weather/current', { adapter })

    expect(captured.config?.headers?.Authorization).toBeUndefined()
  })

  it('请求头为空对象时也能安全写入', async () => {
    localStorage.setItem(TOKEN_KEY, 'token-xyz')
    const { captured, adapter } = captureRequest()

    // 显式传一个空 headers，模拟"调用方没自己设头"的场景
    await http.get('/notes', { adapter, headers: {} })

    expect(captured.config?.headers?.Authorization).toBe('Bearer token-xyz')
  })

  it('baseURL 指向 /api/v1', async () => {
    const { captured, adapter } = captureRequest()

    await http.get('/itinerary', { adapter })

    expect(captured.config?.baseURL).toBe('/api/v1')
  })
})

describe('响应拦截器：解包统一响应体', () => {
  it('code=0 时直接返回 data（调用方不必再剥一层）', async () => {
    const { adapter } = captureRequest({ code: 0, message: '成功', data: { id: 7, title: '白云山' } })

    const result = await http.get('/itinerary/7', { adapter })

    expect(result).toEqual({ id: 7, title: '白云山' })
  })

  it('业务错误码时弹出后端提示并 reject', async () => {
    const { adapter } = captureRequest({ code: 1001, message: '用户名已存在', data: null })

    await expect(http.post('/users/register', {}, { adapter })).rejects.toThrow('用户名已存在')
    expect(message.error).toHaveBeenCalledWith('用户名已存在')
  })

  it('业务错误缺少 message 时给通用兜底文案', async () => {
    const { adapter } = captureRequest({ code: 500, data: null })

    await expect(http.get('/x', { adapter })).rejects.toThrow('请求失败')
    expect(message.error).toHaveBeenCalledWith('请求失败')
  })

  it('非标准响应体（如文件流）原样返回', async () => {
    const { adapter } = captureRequest('raw-content')

    const result = await http.get('/notes/1/export', { adapter })

    expect(result).toBe('raw-content')
  })
})

describe('响应拦截器：错误处理', () => {
  /** 构造一个"服务端返回错误状态码"的 reject */
  function rejectWith(status: number, data: unknown = {}, url = '/itinerary') {
    const err = {
      config: { url },
      response: { status, data },
      code: undefined as string | undefined,
      message: 'Request failed',
    }
    return http.get(url, {
      adapter: () => Promise.reject(err),
    })
  }

  it('401 时清除本地 token 并提示重新登录', async () => {
    localStorage.setItem(TOKEN_KEY, 'expired-token')

    await expect(rejectWith(401)).rejects.toBeTruthy()

    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(message.error).toHaveBeenCalledWith('登录已过期，请重新登录')
  })

  it('登录接口自身失败时不重复弹提示（由登录页展示）', async () => {
    await expect(rejectWith(401, {}, '/users/login')).rejects.toBeTruthy()

    expect(message.error).not.toHaveBeenCalled()
  })

  it('超时给出明确提示', async () => {
    const err = {
      config: { url: '/weather/current' },
      code: 'ECONNABORTED',
      message: 'timeout of 30000ms exceeded',
    }
    await expect(
      http.get('/weather/current', { adapter: () => Promise.reject(err) }),
    ).rejects.toBeTruthy()

    expect(message.error).toHaveBeenCalledWith('请求超时，请稍后重试')
  })

  it('无响应（断网）时提示网络异常', async () => {
    const err = { config: { url: '/news' }, message: 'Network Error' }
    await expect(http.get('/news', { adapter: () => Promise.reject(err) })).rejects.toBeTruthy()

    expect(message.error).toHaveBeenCalledWith('网络异常，请检查网络后重试')
  })

  it('业务错误优先展示后端 detail', async () => {
    await expect(rejectWith(400, { detail: '日期格式应为 YYYY-MM-DD' })).rejects.toBeTruthy()

    expect(message.error).toHaveBeenCalledWith('日期格式应为 YYYY-MM-DD')
  })

  it('后端未给 detail 时使用通用文案', async () => {
    await expect(rejectWith(500)).rejects.toBeTruthy()

    expect(message.error).toHaveBeenCalledWith('服务异常，请稍后重试')
  })
})
