import http from './http'

// ===== 通知基础设施（Day 34）=====

export interface SubscribePayload {
  endpoint: string
  keys: { p256dh: string; auth: string }
  /** 字段名必须与后端 SubscribeIn 一致（user_agent）：
      写成 userAgent 会被 pydantic 直接忽略，设备列表就全成了「未知设备」 */
  user_agent?: string
}

export interface NotificationLogItem {
  id: number
  channel: 'web_push' | 'email'
  /** 通知类型（Day 39）：用来在历史里区分早报/预警/行程提醒 */
  category: NotificationCategory
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

// ===== 每日早报偏好（Day 35）=====

/** 查询早报偏好（未设置过时后端返回默认值：开启、7 点） */
export async function getMorningReport(): Promise<{ enabled: boolean; hour: number }> {
  return (await http.get('/notifications/morning-report')) as unknown as {
    enabled: boolean
    hour: number
  }
}

/** 设置早报开关与推送小时（关闭后分发任务不再推送该用户） */
export async function updateMorningReport(enabled: boolean, hour: number): Promise<void> {
  await http.put('/notifications/morning-report', { enabled, hour })
}

// ===== 通知偏好与订阅管理（Day 39）=====

export type NotificationCategory =
  | 'morning'
  | 'alert'
  | 'itinerary'
  | 'itinerary_risk'
  | 'system'

export interface NotificationPrefs {
  morning_enabled: boolean
  morning_hour: number
  alert_enabled: boolean
  itinerary_enabled: boolean
  /** 行程天气预警（Day 52）：提前 1~3 天告知"预报与已排行程冲突" */
  risk_enabled: boolean
}

export interface SubscriptionItem {
  id: number
  user_agent: string | null
  /** 订阅端点主机（如 web.push.apple.com）：UA 为空时用它兜底认设备 */
  endpoint_host?: string | null
  is_active: boolean
  created_at: string | null
}

/** 读取通知偏好（未设置过时后端返回默认值：全开、7 点） */
export async function getPrefs(): Promise<NotificationPrefs> {
  return (await http.get('/notifications/prefs')) as unknown as NotificationPrefs
}

/** 部分更新通知偏好：只传要改的字段，避免把另一个开关覆盖回旧值 */
export async function updatePrefs(payload: Partial<NotificationPrefs>): Promise<NotificationPrefs> {
  return (await http.put('/notifications/prefs', payload)) as unknown as NotificationPrefs
}

/** 当前账号的推送订阅（一台设备一条） */
export async function listSubscriptions(): Promise<SubscriptionItem[]> {
  const data = (await http.get('/notifications/subscriptions')) as unknown as {
    items: SubscriptionItem[]
  }
  return data.items
}

/** 退订指定设备（按订阅 id，只影响这一台） */
export async function deleteSubscription(id: number): Promise<void> {
  await http.delete(`/notifications/subscriptions/${id}`)
}

// ===== 通知通道状态（Day 43）=====

/** 单条通道的就绪情况：configured=服务端有无能力发，ready=该用户当前能否收到 */
export interface ChannelState {
  configured: boolean
  ready: boolean
}

export interface ChannelStatus {
  web_push: ChannelState & { subscriptions: number }
  email: ChannelState & { bound_email: string | null }
}

/**
 * 查询两条通知通道的就绪状态。
 * 前端据此给出「去绑定邮箱 / 去开启推送」的明确引导，
 * 而不是让用户从发送记录的「用户未绑定邮箱」里自己猜原因。
 */
export async function getChannelStatus(): Promise<ChannelStatus> {
  return (await http.get('/notifications/channels')) as unknown as ChannelStatus
}
