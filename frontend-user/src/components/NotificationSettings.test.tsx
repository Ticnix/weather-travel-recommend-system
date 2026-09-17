import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getPrefs: vi.fn(),
  updatePrefs: vi.fn(),
  listSubscriptions: vi.fn(),
  deleteSubscription: vi.fn(),
  getNotificationLogs: vi.fn(),
  getVapidKey: vi.fn(),
  removeSubscription: vi.fn(),
  saveSubscription: vi.fn(),
  sendTestNotification: vi.fn(),
}))

vi.mock('../api/notifications', () => mocks)

import NotificationSettings from './NotificationSettings'

const BASE_PREFS = {
  morning_enabled: true,
  morning_hour: 7,
  alert_enabled: true,
  itinerary_enabled: true,
}

// antd 组件渲染较重，默认 1s 的等待在多文件并行跑时会被挤爆，
// 这里统一放宽——用例本身不慢，等的是渲染
const FIND = { timeout: 5000 }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getPrefs.mockResolvedValue(BASE_PREFS)
  mocks.updatePrefs.mockImplementation(async (patch: Record<string, unknown>) => ({
    ...BASE_PREFS,
    ...patch,
  }))
  mocks.listSubscriptions.mockResolvedValue([])
  mocks.getNotificationLogs.mockResolvedValue([])
})

/**
 * 通知设置测试（Day 39）。
 *
 * jsdom 里没有 serviceWorker / PushManager，组件会走「当前环境不支持推送」
 * 的分支——这不影响本组用例，要验的是偏好与设备管理这两块。
 */
describe('NotificationSettings', () => {
  it('展示三类推送开关', async () => {
    render(<NotificationSettings />)

    expect(await screen.findByRole('switch', { name: '每日早报' }, FIND)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '天气预警' })).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '行程提醒' })).toBeInTheDocument()
  })

  it('关掉某一类时只提交该字段', async () => {
    render(<NotificationSettings />)
    const alertSwitch = await screen.findByRole('switch', { name: '天气预警' }, FIND)

    await userEvent.click(alertSwitch)

    await waitFor(() => expect(mocks.updatePrefs).toHaveBeenCalledTimes(1))
    // 关键：只提交改动字段。全量提交会把另一个开关覆盖回上一次读到的旧值，
    // 用户快速连点两个开关时就会丢设置。
    expect(mocks.updatePrefs).toHaveBeenCalledWith({ alert_enabled: false })
  })

  it('早报开启时展示可选的推送时间', async () => {
    render(<NotificationSettings />)

    expect(await screen.findByText('07:00', undefined, FIND)).toBeInTheDocument()
  })

  it('没有已订阅设备时给出提示', async () => {
    render(<NotificationSettings />)
    expect(await screen.findByText('当前没有已订阅的设备', undefined, FIND)).toBeInTheDocument()
  })

  it('列出已订阅设备并可退订', async () => {
    mocks.listSubscriptions.mockResolvedValue([
      {
        id: 7,
        user_agent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1',
        is_active: true,
        created_at: '2026-09-16T08:00:00+00:00',
      },
    ])
    render(<NotificationSettings />)

    // UA 要收成一眼能认出的名字，而不是把整串 UA 糊在界面上
    expect(await screen.findByText('iPhone', undefined, FIND)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /退订/ }))
    // 二次确认的按钮文案与触发按钮不同，避免点到同一个元素
    await userEvent.click(await screen.findByRole('button', { name: '确认退订' }, FIND))

    await waitFor(() => expect(mocks.deleteSubscription).toHaveBeenCalledWith(7))
  })

  it('发送记录会标出类型与被拦原因', async () => {
    mocks.getNotificationLogs.mockResolvedValue([
      {
        id: 1,
        channel: 'web_push',
        category: 'alert',
        title: '暴雨红色预警',
        body: null,
        url: null,
        status: 'skipped',
        error: '用户已关闭「天气预警」',
        created_at: '2026-09-16T08:00:00+00:00',
      },
    ])
    render(<NotificationSettings />)

    // 类型标签 + 被偏好拦下的原因都要能看到，
    // 否则用户只会觉得"推送坏了"，查不到其实是自己关的
    expect(await screen.findByText('预警', undefined, FIND)).toBeInTheDocument()
    expect(screen.getByText('用户已关闭「天气预警」')).toBeInTheDocument()
  })
})
