import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, List, Space, Tag, Typography } from 'antd'
import {
  getNotificationLogs,
  getVapidKey,
  removeSubscription,
  saveSubscription,
  sendTestNotification,
  type NotificationLogItem,
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

/**
 * 通知设置区块（Profile 页）。
 *
 * 覆盖 Day 34 检查清单的三条路径：
 * - 已订阅 → 可收推送 + 可测试 + 可退订
 * - 未订阅 → 引导开启（请求浏览器授权）
 * - 已拒绝 → 友好降级：告知去浏览器设置里恢复，而不是反复弹授权
 */
export default function NotificationSettings() {
  const [pushState, setPushState] = useState<PushState>('off')
  const [busy, setBusy] = useState<'enable' | 'disable' | 'test' | null>(null)
  const [logs, setLogs] = useState<NotificationLogItem[]>([])
  const [testResult, setTestResult] = useState<string | null>(null)

  const refreshLogs = useCallback(() => {
    getNotificationLogs()
      .then(setLogs)
      .catch(() => setLogs([]))
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
    void detectState()
    refreshLogs()
  }, [detectState, refreshLogs])

  const enablePush = async () => {
    setBusy('enable')
    try {
      // 1. 请求浏览器通知授权（必须是用户手势触发的调用）
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

      // 3. 把订阅信息交给后端保存（后续服务端用它发推送）
      const json = sub.toJSON()
      await saveSubscription({
        endpoint: sub.endpoint,
        keys: { p256dh: json.keys?.p256dh ?? '', auth: json.keys?.auth ?? '' },
        userAgent: navigator.userAgent.slice(0, 255),
      })
      setPushState('on')
      refreshLogs()
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
    } finally {
      setBusy(null)
    }
  }

  const test = async () => {
    setBusy('test')
    setTestResult(null)
    try {
      const result = await sendTestNotification()
      const summary = Object.values(result)
        .map((r) => `${r.channel}: ${r.status === 'sent' ? '已发送' : r.status === 'skipped' ? '未启用' : '失败'}`)
        .join('，')
      setTestResult(summary)
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
        <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
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

      <Space wrap style={{ marginBottom: logs.length ? 16 : 0 }}>
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

      {logs.length > 0 && (
        <>
          <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>最近发送记录</Text>
          <List
            size="small"
            dataSource={logs}
            renderItem={(log) => (
              <List.Item style={{ padding: '6px 0' }}>
                <Space>
                  <Tag color={log.channel === 'web_push' ? 'magenta' : 'blue'}>
                    {log.channel === 'web_push' ? '网页推送' : '邮件'}
                  </Tag>
                  <Tag color={log.status === 'sent' ? 'green' : log.status === 'failed' ? 'red' : 'default'}>
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
        </>
      )}
    </div>
  )
}
