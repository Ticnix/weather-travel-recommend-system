import { act, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import OfflineNotice from './OfflineNotice'

/**
 * 离线提示测试（Day 38）。
 *
 * 两个关键点：
 * 1. jsdom 的 navigator.onLine 恒为 true，所以必须**同时**改它并派发事件——
 *    真实浏览器断网时也是这两件事一起发生。只派发事件的话，
 *    组件回读 navigator.onLine 会得到 true，提示根本不会出现。
 * 2. 事件派发要包在 act() 里：setState 发生在 React 事件系统之外。
 */
function setNetwork(online: boolean) {
  Object.defineProperty(navigator, 'onLine', { value: online, configurable: true })
  act(() => window.dispatchEvent(new Event(online ? 'online' : 'offline')))
}

describe('OfflineNotice', () => {
  it('在线时不展示任何提示', () => {
    render(<OfflineNotice />)
    expect(screen.queryByTestId('offline-notice')).not.toBeInTheDocument()
  })

  it('断网后展示离线提示且说明是缓存数据', () => {
    render(<OfflineNotice />)

    setNetwork(false)

    const notice = screen.getByTestId('offline-notice')
    // 提示必须说清"看到的是缓存"，否则用户会把不更新当成 bug
    expect(notice).toHaveTextContent('离线')
    expect(notice).toHaveTextContent('缓存')
  })

  it('网络恢复后提示自动消失', () => {
    render(<OfflineNotice />)

    setNetwork(false)
    expect(screen.getByTestId('offline-notice')).toBeInTheDocument()

    setNetwork(true)
    expect(screen.queryByTestId('offline-notice')).not.toBeInTheDocument()
  })

  it('挂载前就已经断网也能正确提示', () => {
    // 事件在组件挂载前就派发过（比如页面还在加载时断网），那次没人听到；
    // 组件挂载后主动与 navigator.onLine 对账，因此仍然要显示
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })

    render(<OfflineNotice />)

    expect(screen.getByTestId('offline-notice')).toBeInTheDocument()
  })
})
