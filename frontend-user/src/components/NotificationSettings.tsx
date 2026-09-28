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
  getChannelStatus,
  getNotificationLogs,
  getPrefs,
  getVapidKey,
  listSubscriptions,
  removeSubscription,
  saveSubscription,
  sendTestNotification,
  updatePrefs,
  type ChannelStatus,
  type NotificationLogItem,
  type NotificationPrefs,
  type SubscriptionItem,
} from '../api/notifications'
import EmailBinding from './EmailBinding'

const { Text } = Typography

/** 校验 / 发送用的通道与状态中文名（测试结果不再直接甩英文枚举给用户） */
const CHANNEL_LABEL: Record<string, string> = { web_push: '网页推送', email: '邮件' }
const STATUS_LABEL: Record<string, string> = { sent: '已发送', skipped: '未发送', failed: '发送失败' }

/** VAPID 公钥是 base64url 字符串，subscribe 需要转成 Uint8Array */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

type PushState = 'unsupported' | 'denied' | 'on' | 'off'

/** iOS 设备（iPadOS 的 Safari 会把 UA 伪装成 Mac，需要额外看触点数） */
function isIOSDevice(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent
  return (
    /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  )
}

/**
 * 是否以「已添加到主屏幕」的独立窗口在运行。
 *
 * iOS 上这是网页推送的**前提条件**：Safari 标签页里 PushManager 根本不存在，
 * 用户点开启必然失败——而系统不会给任何解释。所以我们要自己识别并说清楚，
 * 否则用户只会得出「你们这个推送是坏的」。
 */
function isStandaloneMode(): boolean {
  if (typeof window === 'undefined') return false
  const byMedia = window.matchMedia?.('(display-mode: standalone)').matches === true
  const byLegacy = (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  return byMedia || byLegacy
}

/** 通知类型的中文名与标签色（开关与历史记录共用一套说法） */
const CATEGORY_META: Record<string, { label: string; color: string }> = {
  morning: { label: '早报', color: 'gold' },
  alert: { label: '预警', color: 'red' },
  itinerary: { label: '行程', color: 'geekblue' },
  itinerary_risk: { label: '行程预警', color: 'orange' },
  system: { label: '系统', color: 'default' },
}

/** 四类可关闭的推送（key 与后端偏好字段、日志 category 一一对应） */
const CATEGORY_ROWS: Array<{
  field: 'morning_enabled' | 'alert_enabled' | 'itinerary_enabled' | 'risk_enabled'
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
  {
    // 与「行程提醒」的区别要写清楚：一个提醒你出发，一个提前告诉你别去
    field: 'risk_enabled',
    title: '行程天气预警',
    desc: '提前 1~3 天发现行程与天气冲突，并给出改期建议',
  },
]

const DEFAULT_PREFS: NotificationPrefs = {
  morning_enabled: true,
  morning_hour: 7,
  alert_enabled: true,
  itinerary_enabled: true,
  risk_enabled: true,
}

/** 设备展示名：浏览器 UA 太长，截成一眼能认出的部分 */
function deviceName(ua: string | null, endpointHost?: string | null): string {
  if (!ua) {
    // 老订阅没存 UA（字段名对不上导致的历史数据）：用推送端点兜底，
    // 否则一排「未知设备」等于没做多设备管理
    if (endpointHost?.includes('apple.com')) return 'Apple 推送（iPhone/iPad）'
    if (endpointHost?.includes('googleapis.com')) return 'Google 推送（Chrome/安卓）'
    return '未知设备'
  }
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
  const [channels, setChannels] = useState<ChannelStatus | null>(null)
  // 通道状态 / 订阅设备 / 发送记录各有各的失败：原来一律只是"置空"，
  // 于是页面上的"没有记录"和"没取到"长得一模一样
  const [loadFailed, setLoadFailed] = useState(false)
  // iOS 且没加到主屏幕：这时推送一定开不了，要给出可执行的步骤而不是"不支持"
  const iosNeedsInstall = isIOSDevice() && !isStandaloneMode()

  const refreshLogs = useCallback(() => {
    getNotificationLogs()
      .then(setLogs)
      .catch(() => {
        setLogs([])
        setLoadFailed(true)
      })
  }, [])

  const refreshChannels = useCallback(() => {
    getChannelStatus()
      .then(setChannels)
      .catch(() => {
        setChannels(null)
        setLoadFailed(true)
      })
  }, [])

  const refreshSubs = useCallback(() => {
    listSubscriptions()
      .then(setSubs)
      .catch(() => {
        setSubs([])
        setLoadFailed(true)
      })
  }, [])

  /** 统一刷新：失败提示里的「重试」也走这里 */
  const refreshAll = useCallback(() => {
    setLoadFailed(false)
    refreshLogs()
    refreshSubs()
    refreshChannels()
  }, [refreshChannels, refreshLogs, refreshSubs])

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
      .catch(() => {
        // 取不到就用默认偏好，但要让用户知道"现在显示的是默认值"
        setLoadFailed(true)
      })
    refreshAll()
    void detectState()
  }, [detectState, refreshAll])

  /**
   * 确保 Service Worker 已就绪（active）。
   * autoUpdate 一般会自动注册，但多一层兜底：没有就主动 register 一次。
   * navigator.serviceWorker.ready 在 SW 安装失败时会一直挂起，
   * 这里加 10s 超时，避免按钮转圈到天荒地老却没任何提示。
   */
  const ensureSwReady = useCallback(async (): Promise<ServiceWorkerRegistration> => {
    // 开发服务器不生成 SW（vite-plugin-pwa 的 devOptions.enabled=false）：
    // /sw.js 会落到 SPA 的 index.html，浏览器报
    // "unsupported MIME type (text/html)"。这不是功能坏了，直接说清楚。
    if (import.meta.env.DEV) {
      throw new Error(
        '开发环境（npm run dev）不提供 Service Worker，推送请在正式构建的站点上测试',
      )
    }
    let reg = await navigator.serviceWorker.getRegistration()
    if (!reg) {
      reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' })
    }
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error('Service Worker 未就绪，请刷新页面后重试')), 10000),
    )
    return Promise.race([navigator.serviceWorker.ready, timeout])
  }, [])

  const enablePush = async () => {
    setBusy('enable')
    try {
      // 环境不支持：直接说人话，而不是让按钮点了没反应
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        message.error(
          iosNeedsInstall
            ? 'iPhone / iPad 请先「添加到主屏幕」，再从桌面图标打开本页开启推送'
            : '当前浏览器不支持网页推送，请改用 Chrome / Edge',
        )
        return
      }

      // 1. 请求浏览器通知授权（必须由用户手势触发）
      const permission = await Notification.requestPermission()
      if (permission === 'denied') {
        setPushState('denied')
        message.error('通知权限被拒绝，请在地址栏左侧允许本站通知后重试')
        return
      }
      if (permission !== 'granted') {
        // 用户没在弹窗里选（点了别处 / 关闭）→ 之前是静默 return，现在给个提示
        message.info('未授权通知，未开启推送')
        return
      }

      // 2. 等 Service Worker 就绪 → 用后端下发的 VAPID 公钥订阅
      const reg = await ensureSwReady()
      const publicKey = await getVapidKey()
      if (!publicKey) {
        message.error('服务端未配置推送公钥（VAPID），暂时无法开启网页推送')
        return
      }
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true, // 浏览器规范要求：推送必须伴随可见通知
        applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
      })

      // 3. 订阅信息交给后端保存（后续服务端用它发推送）
      const json = sub.toJSON()
      await saveSubscription({
        endpoint: sub.endpoint,
        keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
        // 字段名跟后端 SubscribeIn 对齐（写 userAgent 会被 pydantic 丢掉）
        user_agent: navigator.userAgent.slice(0, 255),
      })
      setPushState('on')
      refreshLogs()
      refreshSubs()
      refreshChannels()
      message.success('已开启天气推送')
    } catch (err) {
      // 之前这里没有 catch，subscribe 的任何异常都会被静默吞掉 → 用户看到「点了没反应」
      console.error('[enablePush] 开启推送失败：', err)
      message.error('开启推送失败：' + (err instanceof Error ? err.message : String(err)))
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
        Object.entries(result)
          .map(([key, r]) => {
            const label = CHANNEL_LABEL[r.channel] ?? CHANNEL_LABEL[key] ?? r.channel
            const status = STATUS_LABEL[r.status] ?? r.status
            // 带上原因：例如「邮件：未发送（用户未绑定邮箱）」，用户才知道下一步该做什么
            return `${label}：${status}${r.error ? `（${r.error}）` : ''}`
          })
          .join('；'),
      )
      refreshLogs()
      refreshChannels()
    } catch (err) {
      console.error('[test] 发送测试通知失败：', err)
      message.error('发送测试通知失败：' + (err instanceof Error ? err.message : String(err)))
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
        return (
          <Tag color="orange">
            {iosNeedsInstall ? '需先添加到主屏幕' : '当前浏览器不支持推送'}
          </Tag>
        )
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

      {/* 部分信息没取到：不说明的话，"没有记录"和"没取到"看起来完全一样 */}
      {loadFailed && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="部分信息没能加载出来"
          description="通道状态 / 已订阅设备 / 推送偏好 / 发送记录里有一项没取到，下面显示的内容可能不完整，或仍是默认值。"
          action={
            <Button size="small" onClick={refreshAll}>
              重试
            </Button>
          }
        />
      )}

      {/* 通道状态概览：一眼看出哪条通道可用、哪条还需要处理 */}
      {channels && (
        <Space wrap size={20} style={{ marginBottom: 12 }}>
          <Space size={6}>
            <Text style={{ fontSize: 12.5, color: 'var(--jp-ink-3)' }}>网页推送</Text>
            {channels.web_push.ready ? (
              <Tag color="green" style={{ margin: 0 }}>
                已就绪
              </Tag>
            ) : channels.web_push.configured ? (
              <Tag style={{ margin: 0 }}>未开启</Tag>
            ) : (
              <Tag color="orange" style={{ margin: 0 }}>
                服务端未配置
              </Tag>
            )}
          </Space>
          <Space size={6}>
            <Text style={{ fontSize: 12.5, color: 'var(--jp-ink-3)' }}>邮件</Text>
            {channels.email.bound_email ? (
              <Tag color="green" style={{ margin: 0 }}>
                已绑定
              </Tag>
            ) : (
              <Tag color="orange" style={{ margin: 0 }}>
                未绑定邮箱
              </Tag>
            )}
            {/* 已绑定 ≠ 能收到：服务端没配 SMTP 时邮件同样发不出去，
                必须单独标出来，否则用户会像之前那样「明明绑了却收不到」 */}
            {!channels.email.configured && (
              <Tag color="orange" style={{ margin: 0 }}>
                服务端未配置
              </Tag>
            )}
          </Space>
        </Space>
      )}

      {/* iOS 上推送开不了的真正原因：Safari 标签页里不支持，
          必须「添加到主屏幕」后从桌面图标打开（iOS 16.4+）。
          这里把步骤写清楚，不然用户只会以为功能坏了。 */}
      {pushState === 'unsupported' && iosNeedsInstall && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="iPhone / iPad 需要先「添加到主屏幕」才能开推送"
          description="iOS 只在「已添加到主屏幕」的网页应用里支持网页推送（需 iOS 16.4 及以上）。步骤：用 Safari 打开本页 → 点底部「分享」→「添加到主屏幕」→ 从桌面新图标打开本页 → 回到这里点「开启天气推送」。在 Safari 标签页里怎么点都不会成功。"
        />
      )}
      {pushState === 'unsupported' && !iosNeedsInstall && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="当前环境不支持网页推送"
          description="网页推送需要 HTTPS 环境，且浏览器需支持 Service Worker。可换用 Chrome / Edge 等现代浏览器访问。安卓 Chrome 的推送由 Google 推送服务（FCM）转发，部分网络下连不上——那种情况请改用邮件通知。"
        />
      )}
      {pushState === 'denied' && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="通知权限曾被拒绝"
          description={
            iosNeedsInstall || isIOSDevice()
              ? 'iPhone / iPad 上请到「设置 → 通知」里找到本应用（或 Safari）打开通知权限；也可以在 Safari 里点地址栏左侧的「大小 / aA」→「网站设置」→ 通知，改回允许后刷新页面。'
              : '请在浏览器地址栏左侧的锁形图标中，把本站的通知权限改回「允许」，然后刷新页面重新开启。'
          }
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

      {/* 邮箱通知：未绑定时给出明确引导（此前只在发送记录里留一句「未绑定」，用户无处可去） */}
      <EmailBinding
        boundEmail={channels?.email.bound_email ?? null}
        emailConfigured={channels?.email.configured ?? true}
        onChanged={() => {
          refreshChannels()
          refreshLogs()
        }}
      />

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
                  <span style={{ fontSize: 13 }}>
                    {deviceName(item.user_agent, item.endpoint_host)}
                  </span>
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
