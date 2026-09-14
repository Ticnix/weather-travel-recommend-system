import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ForecastDay } from '../api/weather'

// 组件通过 api/weather 取数，这里整体替换掉，测试只关心渲染逻辑
vi.mock('../api/weather', () => ({
  getForecast: vi.fn(),
  getHistory: vi.fn(),
}))

import { getForecast, getHistory } from '../api/weather'
import ForecastList from './ForecastList'

const mockForecast = vi.mocked(getForecast)
const mockHistory = vi.mocked(getHistory)

/** 生成相对今天的日期串（不写死日期，测试才能长期稳定） */
function dateOffset(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function makeDay(
  offset: number,
  desc: string | null,
  tmax: number | null,
  tmin: number | null,
): ForecastDay {
  return {
    date: dateOffset(offset),
    time: dateOffset(offset),
    temp_max: tmax,
    temp_min: tmin,
    weather_desc: desc,
    weather_code: null,
    precipitation: null,
  }
}

/** 未来 7 天预报（今天 + 6 天） */
function forecastDays(): ForecastDay[] {
  return [
    makeDay(0, '雷阵雨', 33, 25),
    makeDay(1, '中雨', 31, 25),
    makeDay(2, '小雨', 32, 26),
    makeDay(3, '阴', 33, 25),
    makeDay(4, '多云', 33, 26),
    makeDay(5, '晴', 34, 26),
    makeDay(6, '晴', 35, 27),
  ]
}

/**
 * 等待时间轴渲染出 n 张卡片。
 *
 * 用「MM-DD」文本计数而不是找「今天」——因为「今天」在**卡片**和**底部图例**
 * 里各出现一次，getByText 会因多处匹配而报错。
 */
async function waitForCards(n: number) {
  await waitFor(() => {
    expect(screen.getAllByText(/^\d{2}-\d{2}$/)).toHaveLength(n)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockForecast.mockResolvedValue({ items: forecastDays(), total: 7 })
  mockHistory.mockResolvedValue({
    items: [makeDay(-1, '小雨', 30, 24), makeDay(-2, '多云', 29, 23)],
    total: 2,
  })
})

describe('ForecastList 天气时间轴', () => {
  it('数据加载完成前显示骨架屏', () => {
    render(<ForecastList />)
    // 加载态下标题已在，但还没有日期卡片
    expect(screen.getByText('天气时间轴')).toBeInTheDocument()
    expect(screen.queryAllByText(/^\d{2}-\d{2}$/)).toHaveLength(0)
  })

  it('默认展示「今天 + 未来一周」共 7 天', async () => {
    render(<ForecastList />)
    await waitForCards(7)
  })

  it('今天固定排在最左侧（打开即见当下）', async () => {
    render(<ForecastList />)
    await waitForCards(7)

    const cards = screen.getAllByText(/^\d{2}-\d{2}$/)
    expect(cards[0]).toHaveTextContent(dateOffset(0).slice(5))
  })

  it('渲染温度与天气描述', async () => {
    render(<ForecastList />)
    await waitForCards(7)

    expect(screen.getAllByText('雷阵雨').length).toBeGreaterThan(0)
    // 「33 / 25」这类温度文本
    expect(screen.getAllByText(/33/).length).toBeGreaterThan(0)
  })

  it('今天之外显示周几标签', async () => {
    render(<ForecastList />)
    await waitForCards(7)

    expect(screen.getAllByText(/^周[一二三四五六日]$/).length).toBe(6)
  })

  it('切换到「近 14 天」后卡片数量增加', async () => {
    const user = userEvent.setup()
    render(<ForecastList />)
    await waitForCards(7)

    await user.click(screen.getByText('近 14 天'))

    await waitForCards(14)
  })

  it('切换到「近 30 天」后包含过去日期与实况标记', async () => {
    const user = userEvent.setup()
    render(<ForecastList />)
    await waitForCards(7)

    await user.click(screen.getByText('近 30 天'))

    await waitForCards(30)
    // 历史实测数据用「实况」标记
    expect(screen.getAllByText('实况').length).toBeGreaterThan(0)
  })

  it('缺少数据的日期显示占位而非空白', async () => {
    // 只给 2 天预报，其余 5 天应显示占位
    mockForecast.mockResolvedValue({
      items: [makeDay(0, '晴', 30, 22), makeDay(1, '多云', 31, 23)],
      total: 2,
    })
    render(<ForecastList />)
    await waitForCards(7)

    expect(screen.getAllByText('暂无')).toHaveLength(5)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('接口失败时不崩溃，降级为占位卡片', async () => {
    mockForecast.mockRejectedValue(new Error('boom'))
    mockHistory.mockRejectedValue(new Error('boom'))

    render(<ForecastList />)

    // 关键：异常被 catch 住，界面仍然完整（7 张占位卡），不是白屏
    await waitForCards(7)
    expect(screen.getAllByText('暂无')).toHaveLength(7)
  })

  it('即使没有历史数据，时间轴依然正常渲染', async () => {
    mockHistory.mockResolvedValue({ items: [], total: 0 })

    render(<ForecastList />)
    await waitForCards(7)
  })

  it('图例说明三个区间的含义', async () => {
    render(<ForecastList />)
    await waitForCards(7)

    expect(screen.getByText('过去 · 实况')).toBeInTheDocument()
    expect(screen.getByText('未来 · 预报')).toBeInTheDocument()
    // 图例中的「今天」与卡片中的「今天」并存，因此这里断言至少两个
    expect(screen.getAllByText('今天').length).toBeGreaterThanOrEqual(2)
  })

  it('「回到今天」按钮始终可见（长区间滑动后可快速定位）', async () => {
    render(<ForecastList />)
    await waitForCards(7)

    expect(screen.getByRole('button', { name: /回到今天/ })).toBeInTheDocument()
  })

  it('今天卡片带有 data-today 标记（供滚动定位使用）', async () => {
    const { container } = render(<ForecastList />)
    await waitForCards(7)

    const todayCard = container.querySelector('[data-today="true"]') as HTMLElement
    expect(todayCard).not.toBeNull()

    // 用 within 限定范围，避免与底部图例里的「今天」冲突。
    // 卡片内部本身有 2 处「今天」：上方星期位 + 下方区间标记位。
    expect(within(todayCard).getAllByText('今天')).toHaveLength(2)
    // 只有今天带该标记，其余 6 天不带
    expect(container.querySelectorAll('[data-today="true"]')).toHaveLength(1)
  })
})
