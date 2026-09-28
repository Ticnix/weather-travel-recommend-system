import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 整体替换接口层。除了城市实测，组件还依赖区级接口（选择分区后才会走到）
// 与区域列表（选择器打开时才拉）——mock 里必须都声明，否则 vitest 会报"没有该导出"
vi.mock('../api/weather', () => ({
  getCurrentWeather: vi.fn(),
  getLocalWeather: vi.fn(),
  listDistricts: vi.fn(),
}))

import { getCurrentWeather } from '../api/weather'
import WeatherHero from './WeatherHero'

const mockGetCurrent = vi.mocked(getCurrentWeather)

const weatherData = {
  location_code: 'gz',
  temperature: 29.9,
  feels_like: 35.2,
  humidity: 78,
  wind_speed: 12,
  wind_direction: '南风',
  weather_code: '104',
  weather_desc: '雷阵雨',
  precipitation: 0.5,
  visibility: 24,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('WeatherHero 首页天气主卡', () => {
  it('加载中显示提示（数据未到时不闪空态）', () => {
    // 永不 resolve 的 Promise，模拟"请求悬着"
    mockGetCurrent.mockReturnValue(new Promise(() => {}))
    render(<WeatherHero />)
    // 只转圈不够：还要说清正在取什么
    expect(screen.getByText(/正在获取实时天气/)).toBeInTheDocument()
  })

  it('展示温度、天气标签与体感', async () => {
    mockGetCurrent.mockResolvedValue(weatherData)
    render(<WeatherHero />)

    await waitFor(() => expect(screen.getByText(/29\.9/)).toBeInTheDocument())
    expect(screen.getByText('雷阵雨')).toBeInTheDocument()
    expect(screen.getByText(/体感 35\.2/)).toBeInTheDocument()
  })

  it('湿度/风速/降水/能见度四个指标齐全', async () => {
    mockGetCurrent.mockResolvedValue(weatherData)
    render(<WeatherHero />)

    await waitFor(() => expect(screen.getByText(/29\.9/)).toBeInTheDocument())
    expect(screen.getByText('湿度')).toBeInTheDocument()
    expect(screen.getByText('风速')).toBeInTheDocument()
    expect(screen.getByText('降水')).toBeInTheDocument()
    expect(screen.getByText('能见度')).toBeInTheDocument()
  })

  it('接口失败时说明失败原因并可重试，而不是只有一句"暂无数据"', async () => {
    mockGetCurrent.mockRejectedValue(new Error('boom'))
    render(<WeatherHero />)

    // "取不到"和"本来就没有"要分开说：否则用户不会想到去重试
    expect(await screen.findByText('天气数据没能取到')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重新获取/ })).toBeInTheDocument()
  })

  it('失败后点重试会重新请求', async () => {
    mockGetCurrent.mockRejectedValueOnce(new Error('boom'))
    mockGetCurrent.mockResolvedValue(weatherData)
    render(<WeatherHero />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /重新获取/ })).toBeInTheDocument(),
    )
    await userEvent.click(screen.getByRole('button', { name: /重新获取/ }))

    await waitFor(() => expect(screen.getByText(/29\.9/)).toBeInTheDocument())
  })

  it('字段缺失时用 -- 占位而不是 undefined', async () => {
    mockGetCurrent.mockResolvedValue({
      ...weatherData,
      temperature: null,
      feels_like: null,
      humidity: null,
      wind_speed: null,
      precipitation: null,
      visibility: null,
    })
    render(<WeatherHero />)

    // 6 处缺失（温度/体感/湿度/风速/降水/能见度）都应渲染为含「--」的占位
    await waitFor(() => expect(screen.getAllByText(/--/).length).toBeGreaterThanOrEqual(6))
    // undefined / null 不应出现在页面上
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument()
    expect(screen.queryByText(/null/)).not.toBeInTheDocument()
  })
})
