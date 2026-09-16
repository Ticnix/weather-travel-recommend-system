import { useEffect, useState } from 'react'
import { Button, Space, Typography } from 'antd'
import { CloseOutlined, DownloadOutlined } from '@ant-design/icons'

const { Text } = Typography

/** beforeinstallprompt 事件（Chromium 专有，TS 标准库里没有） */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISMISS_KEY = 'wt_pwa_install_dismissed'

/**
 * 添加到主屏幕引导（Day 38）。
 *
 * 平台差异必须分清，否则一半用户看不到任何提示：
 * - Chromium：监听 beforeinstallprompt，用户点按钮时才调 prompt()——
 *   浏览器要求安装必须由用户手势触发，不能自动弹
 * - iOS Safari：没有 beforeinstallprompt，只能给「分享 → 添加到主屏幕」的文字指引
 */
export default function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null)
  const [visible, setVisible] = useState(false)
  const [iosHint, setIosHint] = useState(false)

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY)) return
    // 已经是独立窗口说明装过了，不再提示
    if (window.matchMedia?.('(display-mode: standalone)').matches) return

    const ua = navigator.userAgent
    const isIOS = /iPad|iPhone|iPod/.test(ua)
    const isSafari = /^((?!chrome|android|crios|fxios).)*safari/i.test(ua)
    if (isIOS && isSafari) {
      setIosHint(true)
      setVisible(true)
      return
    }

    const onPrompt = (event: Event) => {
      // 阻止浏览器自带的迷你信息条，改用我们自己的引导（可解释、可关闭）
      event.preventDefault()
      setDeferred(event as BeforeInstallPromptEvent)
      setVisible(true)
    }
    const onInstalled = () => {
      setVisible(false)
      localStorage.setItem(DISMISS_KEY, '1')
    }

    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  const dismiss = () => {
    setVisible(false)
    // 记住用户的选择，别每次打开都问一遍
    localStorage.setItem(DISMISS_KEY, '1')
  }

  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    const { outcome } = await deferred.userChoice
    setDeferred(null)
    setVisible(false)
    if (outcome === 'accepted') localStorage.setItem(DISMISS_KEY, '1')
  }

  if (!visible) return null

  return (
    <div
      data-testid="install-prompt"
      className="jp-card"
      style={{
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
      }}
    >
      <Text style={{ flex: 1, minWidth: 220, fontSize: 13 }}>
        {iosHint
          ? '把「天气助手」装到桌面：点底部「分享」按钮 → 选择「添加到主屏幕」'
          : '把「天气助手」装到桌面，打开更快、断网也能看天气'}
      </Text>
      <Space size={8}>
        {!iosHint && (
          <Button type="primary" size="small" icon={<DownloadOutlined />} onClick={() => void install()}>
            添加到主屏幕
          </Button>
        )}
        <Button size="small" type="text" icon={<CloseOutlined />} onClick={dismiss}>
          暂不
        </Button>
      </Space>
    </div>
  )
}
