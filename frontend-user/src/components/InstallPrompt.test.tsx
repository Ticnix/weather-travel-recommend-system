import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InstallPrompt from './InstallPrompt'

const DISMISS_KEY = 'wt_pwa_install_dismissed'

/**
 * 造一个 Chromium 的 beforeinstallprompt 事件并派发（jsdom 不会真的派发）。
 * 必须包在 act() 里：setState 发生在 React 事件系统之外。
 */
function fireInstallPrompt(outcome: 'accepted' | 'dismissed' = 'accepted') {
  const event = new Event('beforeinstallprompt') as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: string }>
  }
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

function mockUserAgent(ua: string) {
  Object.defineProperty(navigator, 'userAgent', { value: ua, configurable: true })
}

describe('InstallPrompt', () => {
  beforeEach(() => {
    localStorage.clear()
    mockUserAgent('Mozilla/5.0 (Windows NT 10.0) Chrome/131.0.0.0 Safari/537.36')
  })

  it('默认不打扰用户（没收到安装事件就不展示）', () => {
    render(<InstallPrompt />)
    expect(screen.queryByTestId('install-prompt')).not.toBeInTheDocument()
  })

  it('浏览器允许安装时展示引导与安装按钮', () => {
    render(<InstallPrompt />)

    fireInstallPrompt()

    expect(screen.getByTestId('install-prompt')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /添加到主屏幕/ })).toBeInTheDocument()
  })

  it('点击安装会调用浏览器的安装弹窗', async () => {
    render(<InstallPrompt />)
    const event = fireInstallPrompt('accepted')

    await userEvent.click(screen.getByRole('button', { name: /添加到主屏幕/ }))

    expect(event.prompt).toHaveBeenCalledTimes(1)
  })

  it('选择暂不后不再展示，并记住这次选择', async () => {
    render(<InstallPrompt />)
    fireInstallPrompt()

    // antd 会把两个字的按钮渲染成「暂 不」，用正则兼容空格
    await userEvent.click(screen.getByRole('button', { name: /暂\s*不/ }))

    expect(screen.queryByTestId('install-prompt')).not.toBeInTheDocument()
    expect(localStorage.getItem(DISMISS_KEY)).toBe('1')
  })

  it('已拒绝过的用户不再看到引导', () => {
    localStorage.setItem(DISMISS_KEY, '1')
    render(<InstallPrompt />)

    fireInstallPrompt()

    expect(screen.queryByTestId('install-prompt')).not.toBeInTheDocument()
  })

  it('iOS Safari 给文字指引而不是安装按钮', () => {
    mockUserAgent(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    )
    render(<InstallPrompt />)

    // iOS 没有 beforeinstallprompt，只能引导用户手动添加
    expect(screen.getByTestId('install-prompt')).toBeInTheDocument()
    expect(screen.getByText(/添加到主屏幕/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /添加到主屏幕/ })).not.toBeInTheDocument()
  })
})
