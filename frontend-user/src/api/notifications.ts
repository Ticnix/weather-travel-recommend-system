import http from './http'

// ===== 通知基础设施（Day 34）=====

export interface SubscribePayload {
  endpoint: string
  keys: { p256dh: string; auth: string }
  userAgent?: string
}

export interface NotificationLogItem {
  id: number
  channel: 'web_push' | 'email'
  title: string
  body: string | null
  url: string | null
  status: 'sent' | 'failed' | 'skipped'
  error: string | null
  created_at: string | null
}

export interface ChannelResult {
  channel: string
  status: 'sent' | 'failed' | 'skipped'
  error: string | null
}

/** 获取 VAPID 公钥（subscribe 的 applicationServerKey） */
export async function getVapidKey(): Promise<string> {
  const data = (await http.get('/notifications/vapid-key')) as unknown as { publicKey: string }
  return data.publicKey
}

/** 保存推送订阅（endpoint 为唯一键，重复订阅会刷新） */
export async function saveSubscription(payload: SubscribePayload): Promise<void> {
  await http.post('/notifications/subscriptions', payload)
}

/** 取消订阅 */
export async function removeSubscription(endpoint: string): Promise<void> {
  await http.post('/notifications/subscriptions/unsubscribe', { endpoint })
}

/** 发送测试通知（走全部可用通道） */
export async function sendTestNotification(): Promise<Record<string, ChannelResult>> {
  const data = (await http.post('/notifications/test')) as unknown as Record<string, ChannelResult>
  return data
}

/** 当前用户的通知发送记录 */
export async function getNotificationLogs(): Promise<NotificationLogItem[]> {
  const data = (await http.get('/notifications/logs', { params: { page_size: 10 } })) as unknown as {
    items: NotificationLogItem[]
  }
  return data.items
}
