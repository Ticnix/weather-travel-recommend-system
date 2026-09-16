import { useEffect, useRef } from 'react'
import { notification } from 'antd'
import { connectAlertStream, type AlertEvent } from '../api/alertStream'
import { isLoggedIn } from '../api/auth'

/**
 * 天气预警实时监听（Day 36）：挂在布局里，全站只需要一个实例。
 *
 * 收到预警时两条提示路径并行：
 * - 站内 antd 通知：不需要任何授权，页面开着就能看到
 * - 浏览器系统通知：需要用户授权，但**页面在后台/最小化时也能弹出**
 * 两者互补，缺一个都会漏掉一部分场景。
 */
export default function AlertStreamListener() {
  const [api, contextHolder] = notification.useNotification()
  // 同一条预警只弹一次：SSE 重连后服务端可能补推，去重避免重复打扰
  const seenRef = useRef<Set<number>>(new Set())

  useEffect(() => {
    if (!isLoggedIn()) return

    const controller = new AbortController()

    const handleAlert = (alert: AlertEvent) => {
      if (seenRef.current.has(alert.id)) return
      seenRef.current.add(alert.id)

      const type = alert.level === 'danger' ? 'error' : alert.level === 'warn' ? 'warning' : 'info'
      api.open({
        key: `alert-${alert.id}`,
        type,
        message: `${alert.city}天气预警：${alert.title}`,
        description: alert.detail ?? '',
        duration: 0, // 预警不自动消失，需要用户确认
        placement: 'topRight',
      })

      // 系统级通知：页面不在前台时唯一能触达用户的通道
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        new Notification(`${alert.city}天气预警：${alert.title}`, {
          body: alert.detail ?? '请关注最新天气信息',
          icon: '/favicon.svg',
        })
      }
    }

    // 断线重连由 connectAlertStream 内部负责，这里只负责在卸载时中断
    void connectAlertStream(handleAlert, { signal: controller.signal })

    return () => controller.abort()
  }, [api])

  return contextHolder
}
