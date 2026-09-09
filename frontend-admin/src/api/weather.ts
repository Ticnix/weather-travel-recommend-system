import http from './http'

export interface HistoryRecord {
  time: string
  location_code: string
  temperature: number | null
  feels_like: number | null
  humidity: number | null
  pressure: number | null
  wind_speed: number | null
  wind_direction: string | null
  weather_code: string | null
  weather_desc: string | null
  precipitation: number | null
  visibility: number | null
  is_forecast: boolean
  temp_max?: number | null
  temp_min?: number | null
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AdminListQuery {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
  keyword?: string
  weather?: string
  forecast?: '' | 'true' | 'false'
}

// 管理端气象时序分页查询
export function adminList(params: AdminListQuery = {}): Promise<PageResult<HistoryRecord>> {
  return http.get('/weather/admin-list', { params: { page: 1, page_size: 20, ...params } })
}

// 手动同步
export function syncNow(): Promise<unknown> {
  return http.post('/weather/sync')
}

// 历史回补（同步过去 N 天）
export function syncHistory(days = 30): Promise<unknown> {
  return http.post(`/weather/sync-history?days=${days}`)
}

// 当前最新实测
export function currentWeather(): Promise<HistoryRecord | null> {
  return http.get('/weather/current')
}

// 7 天预报
export function forecast(): Promise<{ items: HistoryRecord[]; total: number }> {
  return http.get('/weather/forecast')
}

// 最近实测（history）
export function historyList(limit = 30): Promise<{ items: HistoryRecord[]; total: number }> {
  return http.get('/weather/history', { params: { limit } })
}

// 时序统计（按天聚合）
export interface DailyAgg {
  date: string
  temperature_avg: number | null
  humidity_avg: number | null
  precipitation_avg: number | null
}

export function weatherStats(days = 30): Promise<{ items: DailyAgg[]; total: number }> {
  return http.get('/weather/stats', { params: { days } })
}
