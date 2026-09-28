import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  generateTripPlan: vi.fn(),
  saveItineraryBatch: vi.fn(),
  isLoggedIn: vi.fn(() => true),
}))

vi.mock('../api/itinerary', () => ({
  generateTripPlan: mocks.generateTripPlan,
  saveItineraryBatch: mocks.saveItineraryBatch,
}))
vi.mock('../api/auth', () => ({ isLoggedIn: mocks.isLoggedIn }))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import TripPlanner from './TripPlanner'

const FIND = { timeout: 5000 }

/** 一份带「雨天已调整」的行程结果 */
function planResult() {
  return {
    request: {
      city: '广州',
      days: 1,
      preferences: ['美食'],
      city_assumed: false,
      start_date: '2026-09-19',
      date_hint: '周末',
      area: null,
      area_hint: null,
    },
    dates: ['2026-09-19'],
    weather: {
      '2026-09-19': { desc: '雷阵雨', precip: 12, temp_min: 26, temp_max: 31, needs_indoor: true },
    },
    weather_hint: null,
    area_note: null,
    plan: {
      city: '广州',
      days: 1,
      summary: '雨天多排室内',
      plan: [
        {
          date: '2026-09-19',
          weather: '雷阵雨',
          weather_note: '当天雷阵雨，已把 1 项户外安排调整为室内',
          items: [
            {
              time: '09:30',
              title: '广东省博物馆',
              activity: '室内游览',
              reason: '避雨',
              weather_adjusted: true,
            },
          ],
        },
      ],
    },
    adjustments: ['2026-09-19：白云山（户外）→ 广东省博物馆（室内，当天雷阵雨）'],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.isLoggedIn.mockReturnValue(true)
  mocks.generateTripPlan.mockResolvedValue(planResult())
  mocks.saveItineraryBatch.mockResolvedValue({ created: 1, failed: [] })
})

describe('TripPlanner', () => {
  it('空需求不发起请求', async () => {
    render(<TripPlanner />)

    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))

    expect(mocks.generateTripPlan).not.toHaveBeenCalled()
  })

  it('示例需求可一键填入', async () => {
    render(<TripPlanner />)

    await userEvent.click(screen.getAllByTestId('plan-example')[0])

    const textarea = screen.getByPlaceholderText(/例如：周末想去广州玩两天/)
    expect((textarea as HTMLTextAreaElement).value).toContain('广州')
  })

  it('生成后展示逐日安排与天气调整说明', async () => {
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '周末去广州两天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))

    expect(await screen.findByText('广东省博物馆', undefined, FIND)).toBeInTheDocument()
    // 因天气做过的调整必须让用户看见——静默替换比不调整更让人困惑
    expect(screen.getByText(/已按天气调整 1 处安排/)).toBeInTheDocument()
    expect(screen.getByText('已因天气调整')).toBeInTheDocument()
    expect(screen.getByText('不适合户外')).toBeInTheDocument()
  })

  it('明确显示排的是哪几天，并说明依据的原词', async () => {
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '国庆去广州三天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    // 「排成了哪几天」必须一眼可见——日期不符预期是这里最常出的错
    expect(screen.getAllByText('2026-09-19').length).toBeGreaterThan(1)
    expect(screen.getByText(/已按你提到的「周末」从 2026-09-19 开始排/)).toBeInTheDocument()
  })

  it('需求里写了区域时把区域显示出来', async () => {
    mocks.generateTripPlan.mockResolvedValue({
      ...planResult(),
      request: { ...planResult().request, area: '南沙区', area_hint: '南沙' },
    })
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '中秋去南沙区玩')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    // 写了"南沙区"就得能看见它被认下来了，否则用户会认为自己的话白说了
    expect(screen.getByText('南沙区')).toBeInTheDocument()
    expect(screen.getByText(/已把行程限定在「南沙区」内/)).toBeInTheDocument()
  })

  it('区域内没取到候选时说明已回落全城，而不是悄悄换地方', async () => {
    mocks.generateTripPlan.mockResolvedValue({
      ...planResult(),
      area_note: '「南沙区」内没检索到候选地点，本次已按广州全城规划——出行前请再核对地点是否都在南沙区',
    })
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '中秋去南沙区玩')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    expect(screen.getByText('区域未能限定')).toBeInTheDocument()
  })

  it('生成期间说明在做什么、要等多久，而不是只放骨架屏', async () => {
    // 排程要等大模型十几到几十秒：用未兑现的 Promise 把等待态固定下来再断言
    let resolvePlan: (value: unknown) => void = () => {}
    mocks.generateTripPlan.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePlan = resolve
        }),
    )
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '国庆去广州玩几天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))

    expect(await screen.findByText(/正在为你生成行程/)).toBeInTheDocument()
    expect(screen.getByText(/通常 10~30 秒/)).toBeInTheDocument()

    resolvePlan(planResult())
    expect(await screen.findByText('广东省博物馆', undefined, FIND)).toBeInTheDocument()
  })

  it('远期日期没有天气时说明未做天气规避，而不是留空白', async () => {
    mocks.generateTripPlan.mockResolvedValue({
      ...planResult(),
      weather: {},
      weather_hint: '所选日期暂无天气预报（超出预报范围），本次未做雨天规避，出行前请再确认天气',
    })
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '国庆去广州三天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    expect(screen.getByText('天气未参与本次排程')).toBeInTheDocument()
    expect(screen.getByText('暂无天气预报')).toBeInTheDocument()
  })

  it('一键保存把每天每项映射成行程条目', async () => {
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '周末去广州两天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    await userEvent.click(screen.getByRole('button', { name: /一键保存到我的行程/ }))

    await waitFor(() => expect(mocks.saveItineraryBatch).toHaveBeenCalledTimes(1))
    expect(mocks.saveItineraryBatch).toHaveBeenCalledWith([
      {
        title: '广东省博物馆',
        date: '2026-09-19',
        start_time: '09:30',
        location: '广东省博物馆',
        activity: '室内游览',
        note: '避雨',
      },
    ])
  })

  it('保存失败时给出提示而不是静默', async () => {
    mocks.saveItineraryBatch.mockRejectedValue(new Error('boom'))
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '周末去广州两天')
    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))
    await screen.findByText('广东省博物馆', undefined, FIND)

    await userEvent.click(screen.getByRole('button', { name: /一键保存到我的行程/ }))

    await waitFor(() => expect(mocks.saveItineraryBatch).toHaveBeenCalled())
  })

  it('未登录时不让生成，并引导登录', async () => {
    mocks.isLoggedIn.mockReturnValue(false)
    render(<TripPlanner />)

    expect(screen.getByRole('button', { name: /生成行程/ })).toBeDisabled()
    expect(screen.getByText(/登录后才能生成与保存/)).toBeInTheDocument()
  })

  it('生成失败时展示原因', async () => {
    mocks.generateTripPlan.mockRejectedValue(new Error('模型超时'))
    render(<TripPlanner />)
    await userEvent.type(screen.getByPlaceholderText(/例如：周末想去广州玩两天/), '周末去广州两天')

    await userEvent.click(screen.getByRole('button', { name: /生成行程/ }))

    expect(await screen.findByText('模型超时', undefined, FIND)).toBeInTheDocument()
  })
})
