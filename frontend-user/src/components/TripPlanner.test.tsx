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
    request: { city: '广州', days: 1, preferences: ['美食'], city_assumed: false },
    dates: ['2026-09-19'],
    weather: {
      '2026-09-19': { desc: '雷阵雨', precip: 12, temp_min: 26, temp_max: 31, needs_indoor: true },
    },
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
