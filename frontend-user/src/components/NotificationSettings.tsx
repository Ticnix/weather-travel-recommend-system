import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  List,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  deleteSubscription,
  getNotificationLogs,
  getPrefs,
  getVapidKey,
  listSubscriptions,
  removeSubscription,
  saveSubscription,
  sendTestNotification,
  updatePrefs,
  type NotificationLogItem,
  type NotificationPrefs,
  type SubscriptionItem,
} from '../api/notifications'

const { Text } = Typography

/** VAPID 公钥是 base64url 字符串，subscribe 需要转成 Uint8Array */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

type PushState = 'unsupported' | 'denied' | 'on' | 'off'

/** 通知类型的中文名与标签色（开关与历史记录共用一套说法） */
const CATEGORY_META: Record<string, { label: string; color: string }> = {
  morning: { label: '早报', color: 'gold' },
  alert: { label: '预警', color: 'red' },
  itinerary: { label: '行程', color: 'geekblue' },
  system: { label: '系统', color: 'default' },
}

/** 三类可关闭的推送（key 与后端偏好字段、日志 category 一一对应） */
const CATEGORY_ROWS: Array<{
  field: 'morning_enabled' | 'alert_enabled' | 'itinerary_enabled'
  title: string
  desc: string
}> = [
  {
    field: 'morning_enabled',
    title: '每日早报',
    desc: '每天一次：今日天气、提醒、穿搭与行程冲突',
  },
  { field: 'alert_enabled', title: '天气预警', desc: '台风、暴雨等预警发布后立即通知' },
  { field: 'itinerary_enabled', title: '行程提醒', desc: '行程开始前 30 分钟提醒，避免错过安排' },
]

const DEFAULT_PREFS: NotificationPrefs = {
  morning_enabled: true,
  morning_hour: 7,
  alert_enabled: true,
  itinerary_enabled: true,
}

/** 设备展示名：浏览器 UA 太长，截成一眼能认出的部分 */
function deviceName(ua: string | null): string {
  if (!ua) return '未知设备'
  const rules: Array<[RegExp, string]> = [
    [/iPhone/, 'iPhone'],
    [/iPad/, 'iPad'],
    [/Android/, 'Android 设备'],
    [/Macintosh/, 'Mac'],
    [/Windows/, 'Windows'],
    [/Linux/, 'Linux'],
  ]
  for (const [pattern, label] of rules) {
    if (pattern.test(ua)) return label
  }
  return '浏览器'
}

/**
 * 通知设置区块（Profile 页）。
 *
 * Day 34 打通了订阅链路，Day 35 加了早报时间，Day 39 补齐三件事：
 * 1. **按类型开关**（早报 / 预警 / 行程提醒）——只能全开全关，等于没有选择权
 * 2. **多设备订阅管理**——只给一个「关闭推送」按钮，用户不知道关的是哪台设备
 * 3. **历史记录带类型**——出问题时能立刻分辨是哪一类没收到
 */
export default function NotificationSettings() {
  const [pushState, setPushState] = useState<PushState>('off')
  const [busy, setBusy] = useState<'enable' | 'disable' | 'test' | null>(null)
  const [logs, setLogs] = useState<NotificationLogItem[]>([])
  const [testResult, setTestResult] = useState<string | null>(null)
  const [prefs, setPrefs] = useState<NotificationPrefs>(DEFAULT_PREFS)
  const [prefSaving, setPrefSaving] = useState(false)
  const [subs, setSubs] = useState<SubscriptionItem[]>([])

  const refreshLogs = useCallback(() => {
    getNotificationLogs()
      .then(setLogs)
      .catch(() => setLogs([]))
  }, [])

  const refreshSubs = useCallback(() => {
    listSubscriptions()
      .then(setSubs)
      .catch(() => setSubs([]))
  }, [])

  const detectState = useCallback(async () => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPushState('unsupported')
      return
    }
    if (typeof Notification === 'undefined') {
      setPushState('unsupported')
      return
    }
    if (Notification.permission === 'denied') {
      setPushState('denied')
      return
    }
    const reg = await navigator.serviceWorker.getRegistration()
    const sub = await reg?.pushManager.getSubscription()
    setPushState(sub ? 'on' : 'off')
  }, [])

  useEffect(() => {
    getPrefs()
      .then(setPrefs)
      .catch(() => {})
    refreshLogs()
    refreshSubs()
    void detectState()
  }, [detectState, refreshLogs, refreshSubs])

  const enablePush = async () => {
    setBusy('enable')
    try {
      // 1. 请求浏览器通知授权（必须由用户手势触发）
      const permission = await Notification.requestPermission()
      if (permission === 'denied') {
        setPushState('denied')
        return
      }
      if (permission !== 'granted') return // dismissed：用户没选，保持原状

      // 2. 等 Service Worker 就绪 → 用后端下发的 VAPID 公钥订阅
      const reg = await navigator.serviceWorker.ready
      const publicKey = await getVapidKey()
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true, // 浏览器规范要求：推送必须伴随可见通知
        applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
      })

      // 3. 订阅信息交给后端保存（后续服务端用它发推送）
      const json = sub.toJSON()
      await saveSubscription({
        endpoint: sub.endpoint,
        keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
        userAgent: navigator.userAgent.slice(0, 255),
      })
      setPushState('on')
      refreshLogs()
      refreshSubs()
    } finally {
      setBusy(null)
    }
  }

  const disablePush = async () => {
    setBusy('disable')
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      const sub = await reg?.pushManager.getSubscription()
      if (sub) {
        await removeSubscription(sub.endpoint)
        await sub.unsubscribe()
      }
      setPushState('off')
      refreshLogs()
      refreshSubs()
    } finally {
      setBusy(null)
    }
  }

  /** 保存偏好：只提交改动的字段，避免把另一个开关覆盖回旧值 */
  const savePrefs = async (patch: Partial<NotificationPrefs>) => {
    setPrefSaving(true)
    try {
      setPrefs(await updatePrefs(patch))
    } catch {
      message.error('保存失败，请稍后重试')
    } finally {
      setPrefSaving(false)
    }
  }

  const removeDevice = async (id: number) => {
    try {
      await deleteSubscription(id)
      refreshSubs()
      // 退订的可能正是当前这台：重新探测，避免开关还显示「已开启」
      await detectState()
      message.success('已退订该设备')
    } catch {
      message.error('退订失败，请稍后重试')
    }
  }

  const test = async () => {
    setBusy('test')
    setTestResult(null)
    try {
      const result = await sendTestNotification()
      setTestResult(
        Object.values(result)
          .map(
            (r) =>
              `${r.channel}: ${
                r.status === 'sent' ? '已发送' : r.status === 'skipped' ? '未启用' : '失败'
              }`,
          )
          .join('，'),
      )
      refreshLogs()
    } finally {
      setBusy(null)
    }
  }

  const stateTag = () => {
    switch (pushState) {
      case 'on':
        return <Tag color="green">推送已开启</Tag>
      case 'denied':
        return <Tag color="red">通知权限已被拒绝</Tag>
      case 'unsupported':
        return <Tag color="orange">当前浏览器不支持推送</Tag>
      default:
        return <Tag>未开启</Tag>
    }
  }

  return (
    <div className="jp-card" style={{ padding: 24 }}>
      <div style={{ marginBottom: 12 }}>
        <span
          className="jp-serif"
          style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
        >
          通知设置
        </span>
        <span style={{ marginLeft: 10 }}>{stateTag()}</span>
      </div>

      {pushState === 'unsupported' && (
        <Alert
          type="warning"
          showIcon
          message="当前环境不支持网页推送"
          description="网页推送需要 HTTPS 环境，且浏览器需支持 Service Worker。可换用 Chrome / Edge 等现代浏览器访问。"
        />
      )}
      {pushState === 'denied' && (
        <Alert
          type="warning"
          showIcon
          message="通知权限曾被拒绝"
          description="请在浏览器地址栏左侧的锁形图标中，把本站的通知权限改回「允许」，然后刷新页面重新开启。"
        />
      )}

      <Space wrap style={{ marginBottom: 8 }}>
        {pushState === 'on' ? (
          <Button danger loading={busy === 'disable'} onClick={disablePush}>
            关闭推送
          </Button>
        ) : (
          <Button
            type="primary"
            loading={busy === 'enable'}
            disabled={pushState === 'unsupported' || pushState === 'denied'}
            onClick={enablePush}
          >
            开启天气推送
          </Button>
        )}
        <Button loading={busy === 'test'} onClick={test}>
          发送测试通知
        </Button>
        <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
          开启后，台风预警、暴雨提醒等关键天气变化会第一时间推送给你。
        </Text>
      </Space>

      {testResult && (
        <Alert type="info" showIcon message={`测试结果：${testResult}`} style={{ marginBottom: 16 }} />
      )}

      {/* 推送类型：按类型关闭，而不是只能全开全关 */}
      <div style={{ borderTop: '1px solid var(--jp-border)', paddingTop: 14, marginTop: 8 }}>
        <Text style={{ fontSize: 13.5, fontWeight: 600 }}>推送类型</Text>
        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)', marginLeft: 8 }}>
          只留你真正需要的，其余关掉就不会再打扰
        </Text>
        <div style={{ marginTop: 8 }}>
          {CATEGORY_ROWS.map((row) => (
            <div
              key={row.field}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                flexWrap: 'wrap',
                padding: '5px 0',
              }}
            >
              <Switch
                size="small"
                // aria-label：开关旁边只是视觉上的文字，读屏与测试都拿不到名字
                aria-label={row.title}
                checked={prefs[row.field]}
                loading={prefSaving}
                onChange={(checked) =>
                  void savePrefs({ [row.field]: checked } as Partial<NotificationPrefs>)
                }
              />
              <span style={{ fontSize: 13.5, color: 'var(--jp-ink)', minWidth: 64 }}>
                {row.title}
              </span>
              <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>{row.desc}</Text>
              {row.field === 'morning_enabled' && prefs.morning_enabled && (
                <Space size={6}>
                  <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>推送时间</Text>
                  <Select
                    size="small"
                    value={prefs.morning_hour}
                    style={{ width: 96 }}
                    disabled={prefSaving}
                    onChange={(hour) => void savePrefs({ morning_hour: hour })}
                    options={Array.from({ length: 18 }, (_, i) => i + 5).map((h) => ({
                      value: h,
                      label: `${String(h).padStart(2, '0')}:00`,
                    }))}
                  />
                </Space>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 推送设备：每台设备独立订阅，可单独退订 */}
      <div style={{ borderTop: '1px solid var(--jp-border)', paddingTop: 14, marginTop: 8 }}>
        <Text style={{ fontSize: 13.5, fontWeight: 600 }}>推送设备</Text>
        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)', marginLeft: 8 }}>
          换手机 / 换浏览器会各算一台，可分别退订
        </Text>
        {subs.length === 0 ? (
          <div style={{ marginTop: 8 }}>
            <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>当前没有已订阅的设备</Text>
          </div>
        ) : (
          <List
            size="small"
            dataSource={subs}
            renderItem={(item) => (
              <List.Item
                style={{ padding: '6px 0' }}
                actions={[
                  <Popconfirm
                    key="remove"
                    title="退订这台设备？"
                    description="退订后该设备不再收到任何推送"
                    okText="确认退订"
                    cancelText="取消"
                    onConfirm={() => void removeDevice(item.id)}
                  >
                    <Button size="small" type="link" danger>
                      退订
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <Space size={8}>
                  <span style={{ fontSize: 13 }}>{deviceName(item.user_agent)}</span>
                  <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                    {item.created_at
                      ? new Date(item.created_at).toLocaleDateString('zh-CN')
                      : ''}
                  </Text>
                </Space>
              </List.Item>
            )}
          />
        )}
      </div>

      {/* 最近发送记录：带类型标签，一眼看出是哪一类没收到 */}
      {logs.length > 0 && (
        <div style={{ borderTop: '1px solid var(--jp-border)', paddingTop: 14, marginTop: 8 }}>
          <Text style={{ fontSize: 13.5, fontWeight: 600 }}>最近发送记录</Text>
          <List
            size="small"
            dataSource={logs}
            renderItem={(log) => (
              <List.Item style={{ padding: '6px 0' }}>
                <Space wrap size={6}>
                  <Tag color={log.channel === 'web_push' ? 'magenta' : 'blue'}>
                    {log.channel === 'web_push' ? '网页推送' : '邮件'}
                  </Tag>
                  <Tag color={CATEGORY_META[log.category]?.color ?? 'default'}>
                    {CATEGORY_META[log.category]?.label ?? log.category}
                  </Tag>
                  <Tag
                    color={
                      log.status === 'sent' ? 'green' : log.status === 'failed' ? 'red' : 'default'
                    }
                  >
                    {log.status === 'sent' ? '已发送' : log.status === 'failed' ? '失败' : '跳过'}
                  </Tag>
                  <span style={{ fontSize: 13 }}>{log.title}</span>
                  {log.error && (
                    <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>{log.error}</Text>
                  )}
                </Space>
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  )
}
