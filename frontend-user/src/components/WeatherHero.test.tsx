import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 组件只依赖 getCurrentWeather 一个接口，整体替换
vi.mock('../api/weather', () => ({
  getCurrentWeather: vi.fn(),
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
    expect(screen.getByText('正在获取实时天气...')).toBeInTheDocument()
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

  it('接口失败显示空态而不是白屏', async () => {
    mockGetCurrent.mockRejectedValue(new Error('boom'))
    render(<WeatherHero />)

    await waitFor(() =>
      expect(screen.getByText('暂无天气数据，请稍后刷新')).toBeInTheDocument(),
    )
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
