import { useEffect, useState } from 'react'
import { DisconnectOutlined } from '@ant-design/icons'

/**
 * 离线状态提示（Day 38）。
 *
 * 断网时 Service Worker 会从缓存里拿应用外壳与最近的天气数据，页面本身能打开——
 * 但用户需要知道「看到的是缓存、可能是旧的」，否则会把「数据不更新」当成 bug。
 *
 * 做成常驻细横条：不遮内容、不需要用户操作，网络恢复后自动消失。
 */
export default function OfflineNotice() {
  const [offline, setOffline] = useState(() => !navigator.onLine)

  useEffect(() => {
    // 挂载后再与 navigator.onLine 对一次账：
    // offline 事件完全可能在本组件挂载**之前**就派发过了（比如页面还在加载时断网），
    // 那一次事件没人听到，只靠监听会一直显示"在线"。
    const sync = () => setOffline(!navigator.onLine)
    sync()

    window.addEventListener('offline', sync)
    window.addEventListener('online', sync)
    return () => {
      window.removeEventListener('offline', sync)
      window.removeEventListener('online', sync)
    }
  }, [])

  if (!offline) return null

  return (
    <div
      data-testid="offline-notice"
      role="status"
      style={{
        background: '#fdf3e3',
        borderBottom: '1px solid #f0dcbb',
        color: '#8a5a1f',
        fontSize: 13,
        padding: '6px 16px',
        textAlign: 'center',
      }}
    >
      <DisconnectOutlined /> 当前处于离线状态，展示的是最近缓存的数据，网络恢复后会自动更新
    </div>
  )
}
