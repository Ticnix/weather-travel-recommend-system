/**
 * 预警实时通道客户端（SSE over fetch）。
 *
 * 为什么不用原生 EventSource：
 *   EventSource 无法自定义请求头，只能把 token 塞进 URL——
 *   token 出现在 URL 里会进 Nginx access log 与浏览器历史，不适合。
 *   fetch + ReadableStream 可以正常携带 Authorization 头。
 * 代价：SSE 协议的分行解析与断线重连都要自己写（本文件就是这部分）。
 */

export interface AlertEvent {
  event: 'weather_alert'
  id: number
  city: string
  level: 'info' | 'warn' | 'danger'
  alert_type: string
  title: string
  detail: string | null
  at: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const TOKEN_KEY = 'wt_token'

/** 指数退避重连：2s → 4s → … → 最长 30s，避免服务端刚重启时被反复冲击 */
const INITIAL_RETRY_MS = 2000
const MAX_RETRY_MS = 30_000

export interface StreamOptions {
  signal: AbortSignal
  onStateChange?: (state: 'open' | 'closed') => void
}

/**
 * 连接预警实时通道，收到预警时回调 onAlert。
 *
 * 该函数在连接断开后会自动重连，直到 signal 被 abort——
 * 调用方只需在组件卸载时 abort 即可。
 */
export async function connectAlertStream(
  onAlert: (alert: AlertEvent) => void,
  { signal, onStateChange }: StreamOptions,
): Promise<void> {
  let retryDelay = INITIAL_RETRY_MS

  while (!signal.aborted) {
    try {
      const token = localStorage.getItem(TOKEN_KEY)
      if (!token) return // 未登录不建立连接

      const resp = await fetch(`${API_BASE}/notifications/stream`, {
        headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
        signal,
      })
      if (!resp.ok || !resp.body) throw new Error(`SSE 连接失败: ${resp.status}`)

      onStateChange?.('open')
      retryDelay = INITIAL_RETRY_MS // 连上过就把退避重置

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE 以空行分隔消息；最后一段可能是半条消息，留在 buffer 里
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''

        for (const chunk of chunks) {
          const dataLine = chunk.split('\n').find((line) => line.startsWith('data:'))
          if (!dataLine) continue // 注释行（以 : 开头）直接跳过
          try {
            const parsed = JSON.parse(dataLine.slice(5).trim()) as Partial<AlertEvent> & {
              type?: string
            }
            // 通道里除了预警还有心跳（{"type":"ping"}）等消息：
            // 必须按 event 字段过滤，否则会把心跳当成预警弹出来
            if (parsed.event === 'weather_alert') onAlert(parsed as AlertEvent)
          } catch {
            // 坏数据不该中断整条连接，忽略这条继续
          }
        }
      }
    } catch {
      // 网络异常 / 服务重启：走下面的重连逻辑
    }

    onStateChange?.('closed')
    if (signal.aborted) return

    await new Promise((resolve) => setTimeout(resolve, retryDelay))
    retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS)
  }
}
